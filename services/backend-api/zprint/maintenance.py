"""Run periodically to enforce document retention. Metadata is retained for audit."""
import time
from sqlalchemy import select
from zprint.config import Settings
from zprint.db import connect
from zprint.models import Document, now


def cleanup(factory, directory):
    with factory.begin() as db:
        docs = db.scalars(select(Document).where(Document.expires_at <= now(), Document.deleted_at.is_(None))).all()
        for doc in docs:
            (directory / doc.storage_key).unlink(missing_ok=True)
            doc.deleted_at = now()
        # A killed upload may leave an untracked file; sweep only after the maximum retention.
        known = set(db.scalars(select(Document.storage_key)).all())
        for path in directory.iterdir():
            if path.is_file() and path.suffix in (".upload", ".pdf") and path.name not in known and path.stat().st_mtime < time.time() - 86400:
                path.unlink()
        return len(docs)


if __name__ == "__main__":
    cfg = Settings()
    cfg.validate()
    _, factory = connect(cfg.database_url)
    while True:
        print(f"Retention cleanup: {cleanup(factory, cfg.data_dir)} documents", flush=True)
        time.sleep(30)
