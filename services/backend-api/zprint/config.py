import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Settings:
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", "sqlite:///./data/zprint.db"))
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("ZPRINT_DATA_DIR", "data")))
    demo: bool = field(default_factory=lambda: os.getenv("ZPRINT_DEMO", "true").lower() == "true")
    admin_key: str = field(default_factory=lambda: os.getenv("ZPRINT_ADMIN_KEY", "local-demo-admin-change-me"))
    agent_key: str = field(default_factory=lambda: os.getenv("ZPRINT_AGENT_KEY", "local-demo-agent-change-me"))
    webhook_secret: str = field(default_factory=lambda: os.getenv("ZPRINT_WEBHOOK_SECRET", "local-demo-webhook-change-me"))
    station: str = field(default_factory=lambda: os.getenv("ZPRINT_STATION", "ST001"))
    max_upload: int = 20 * 1024 * 1024
    max_pages: int = 500
    max_sides: int = 2000
    retention_seconds: int = 86400
    heartbeat_ttl: int = 45

    def validate(self):
        # No live integrations exist yet: fail closed instead of using mocks in production.
        if not self.demo:
            raise RuntimeError("Phase 1 supports DEMO mode only. Live adapters/security review are required.")
        self.data_dir.mkdir(parents=True, exist_ok=True)
