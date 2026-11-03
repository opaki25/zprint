"""Single-instance hosted DEMO process manager.

The API, retention service and fake printer share a durable disk. A failed child
ends the deployment process so the host restarts the whole group; it must not
leave a healthy-looking API with a dead print worker. Real hardware stays local.
"""
import logging
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

import httpx
from alembic import command
from alembic.config import Config

from zprint.config import Settings
from zprint.db import connect
from zprint.seed import seed

log = logging.getLogger("zprint.hosted")
ROOT = Path(os.getenv("ZPRINT_PROJECT_ROOT", str(Path.cwd()))).resolve()


def initialize(settings):
    settings.validate()
    # Run at service startup, when the persistent disk is mounted, not during build.
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "database" / "migrations"))
    # Alembic uses DATABASE_URL from the environment. Avoid logging the DSN/password.
    command.upgrade(config, "head")
    engine, factory = connect(settings.database_url)
    try:
        seed(factory, settings.station)
    finally:
        engine.dispose()


def stop_children(children):
    for _, process in reversed(children):
        if process.poll() is None:
            process.terminate()
    deadline = time.monotonic() + 10
    for _, process in reversed(children):
        try:
            process.wait(timeout=max(0.1, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def first_exited(children):
    return next(((name, process.returncode) for name, process in children if process.poll() is not None), None)


def wait_for_api(url, api_process, stop_event, seconds=60):
    deadline = time.monotonic() + seconds
    with httpx.Client(timeout=2) as client:
        while not stop_event.is_set() and time.monotonic() < deadline:
            if api_process.poll() is not None:
                raise RuntimeError("Backend exited before becoming healthy")
            try:
                if client.get(url + "/health").status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            stop_event.wait(0.5)
    raise RuntimeError("Backend failed its startup health check")


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = Settings()
    if not settings.hosted:
        raise RuntimeError("Use ZPRINT_HOSTED=true for the hosted process manager")
    initialize(settings)
    port = int(os.getenv("PORT", "10000"))
    if not 1 <= port <= 65535:
        raise RuntimeError("PORT must be between 1 and 65535")
    local_url = f"http://127.0.0.1:{port}"
    stopped = threading.Event()
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: stopped.set())
    children = []
    # Child processes inherit only this service's environment; credentials never enter CLI args.
    child_env = os.environ.copy()
    child_env["ZPRINT_API_URL"] = local_url
    child_env.setdefault("ZPRINT_AGENT_DIR", str(settings.data_dir.parent / "agent"))
    try:
        api = subprocess.Popen([sys.executable, "-m", "uvicorn", "zprint.main:app", "--host", "0.0.0.0", "--port", str(port)], env=child_env, cwd=ROOT)
        children.append(("backend", api))
        wait_for_api(local_url, api, stopped)
        for name, module in (("retention", "zprint.maintenance"), ("simulated-printer", "zprint_agent.worker")):
            children.append((name, subprocess.Popen([sys.executable, "-m", module], env=child_env, cwd=ROOT)))
        log.info("Hosted simulation started; no real payments or physical printer")
        while not stopped.wait(1):
            failure = first_exited(children)
            if failure:
                log.error("Service %s exited (code %s); stopping group for host restart", *failure)
                return 1
        return 0
    finally:
        stop_children(children)


if __name__ == "__main__":
    raise SystemExit(main())
