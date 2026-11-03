import hashlib
import json
import logging
import os
import sqlite3
import time
import uuid
from pathlib import Path
import httpx
from zprint_agent.printer import SimulatedPrinter

log = logging.getLogger("zprint.agent")


class AgentWorker:
    def __init__(self, client, directory, printer=None):
        self.client, self.directory = client, Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.printer = printer or SimulatedPrinter(self.directory / "spool")
        self.db = sqlite3.connect(self.directory / "queue.db")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, state TEXT NOT NULL, spooler_id TEXT, updated_at INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS outbox (id TEXT PRIMARY KEY, job_id TEXT NOT NULL, payload TEXT NOT NULL, delivered INTEGER NOT NULL DEFAULT 0);
        """)
        self.recover()

    def enqueue(self, job_id, state, spooler_id=None, detail=""):
        event_id = str(uuid.uuid4())
        payload = dict(event_id=event_id, state=state, spooler_job_id=spooler_id, detail=detail)
        with self.db:
            self.db.execute("UPDATE jobs SET state=?,spooler_id=?,updated_at=? WHERE id=?", (state, spooler_id, int(time.time()), job_id))
            self.db.execute("INSERT INTO outbox(id,job_id,payload) VALUES(?,?,?)", (event_id, job_id, json.dumps(payload)))

    def recover(self):
        for job_id, in self.db.execute("SELECT id FROM jobs WHERE state IN ('CLAIMED','DISPATCHING')").fetchall():
            self.enqueue(job_id, "COMPLETION_UNCERTAIN", detail="Agent restarted during a claim/dispatch; operator inspection required")
        for path in self.directory.glob("*.download.pdf"):
            path.unlink(missing_ok=True)

    def flush(self):
        for event_id, job_id, payload in self.db.execute("SELECT id,job_id,payload FROM outbox WHERE delivered=0 ORDER BY rowid").fetchall():
            response = self.client.post(f"/api/v1/agent/jobs/{job_id}/events", json=json.loads(payload))
            response.raise_for_status()
            with self.db:
                self.db.execute("UPDATE outbox SET delivered=1 WHERE id=?", (event_id,))

    def cleanup(self):
        cutoff = int(time.time()) - 60
        for job_id, spooler_id in self.db.execute("SELECT id,spooler_id FROM jobs WHERE state='COMPLETED' AND updated_at<?", (cutoff,)).fetchall():
            if spooler_id:
                (self.directory / "spool" / spooler_id).unlink(missing_ok=True)
        # Also expire uncertain/partial simulated output within the 24-hour privacy bound.
        for path in (self.directory / "spool").glob("*.pdf"):
            if path.stat().st_mtime < time.time() - 86400:
                path.unlink(missing_ok=True)

    def tick(self):
        self.cleanup()
        self.flush()  # Durable events drain before any new claim.
        ready = self.printer.readiness()
        response = self.client.post("/api/v1/agent/heartbeat", json=ready)
        response.raise_for_status()
        if ready["state"] != "READY":
            return None
        response = self.client.get("/api/v1/agent/jobs/next")
        response.raise_for_status()
        job = response.json()["job"]
        if not job:
            return None
        job_id = job["id"]
        # A single local agent process owns this database. No automatic redispatch after a crash.
        with self.db:
            self.db.execute("INSERT INTO jobs VALUES(?, 'CLAIMED', NULL, ?)", (job_id, int(time.time())))
        document = self.directory / f"{job_id}.download.pdf"
        dispatch_started = False
        try:
            response = self.client.get(job["document_url"])
            response.raise_for_status()
            if hashlib.sha256(response.content).hexdigest() != job["sha256"]:
                raise ValueError("Document checksum mismatch")
            document.write_bytes(response.content)
            if self.printer.readiness()["state"] != "READY":
                self.enqueue(job_id, "PAUSED", detail="Printer unavailable before dispatch")
                self.flush()
                return job_id
            # Persist intent before submitting. An interrupted operation is uncertain, never retried.
            with self.db:
                self.db.execute("UPDATE jobs SET state='DISPATCHING' WHERE id=?", (job_id,))
            started = dict(event_id=str(uuid.uuid4()), state="PRINTING", detail="Simulated dispatch intent")
            response = self.client.post(f"/api/v1/agent/jobs/{job_id}/events", json=started)
            response.raise_for_status()
            dispatch_started = True
            spooler_id = self.printer.submit(job_id, document, job["settings"])
            state = "COMPLETED" if self.printer.status(spooler_id) == "SIMULATED_COMPLETE" else "COMPLETION_UNCERTAIN"
            self.enqueue(job_id, state, spooler_id, "Simulation only; no physical pages produced")
            self.flush()
            log.info("job=%s state=%s", job_id, state)
        except Exception:
            current = self.db.execute("SELECT state FROM jobs WHERE id=?", (job_id,)).fetchone()[0]
            # If a terminal event is already durable, preserve it for replay; do not manufacture a new outcome.
            if current in ("CLAIMED", "DISPATCHING"):
                self.enqueue(job_id, "COMPLETION_UNCERTAIN" if dispatch_started or current == "DISPATCHING" else "PAUSED", detail="Interrupted processing; manual review required")
            raise
        finally:
            document.unlink(missing_ok=True)
        return job_id

    def close(self):
        self.db.close()


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    directory = Path(os.getenv("ZPRINT_AGENT_DIR", "data/agent"))
    directory.mkdir(parents=True, exist_ok=True)
    # OS lock prevents two services sharing the same local queue, including after restart.
    lock = (directory / "agent.lock").open("a+b")
    lock.write(b"0")
    lock.flush()
    lock.seek(0)
    if os.name == "nt":
        import msvcrt
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    with httpx.Client(base_url=os.getenv("ZPRINT_API_URL", "http://127.0.0.1:8000"),
                      headers={"X-Agent-Key": os.getenv("ZPRINT_AGENT_KEY", "local-demo-agent-change-me")}, timeout=30) as client:
        worker = AgentWorker(client, directory)
        try:
            while True:
                try:
                    worker.tick()
                except (httpx.HTTPError, ValueError, RuntimeError, OSError):
                    log.warning("Agent cycle paused; connection, readiness or operator review required")
                time.sleep(3)
        finally:
            worker.close()
            lock.close()


if __name__ == "__main__":
    main()
