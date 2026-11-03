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
    hosted: bool = field(default_factory=lambda: os.getenv("ZPRINT_HOSTED", "false").lower() == "true")
    gateway_key: str = field(default_factory=lambda: os.getenv("ZPRINT_GATEWAY_KEY", ""))
    max_upload: int = 20 * 1024 * 1024
    max_pages: int = 500
    max_sides: int = 2000
    retention_seconds: int = 86400
    heartbeat_ttl: int = 45

    def validate(self):
        # No live integrations exist yet: fail closed instead of using mocks in production.
        if not self.demo:
            raise RuntimeError("Phase 1 supports DEMO mode only. Live adapters/security review are required.")
        if self.hosted:
            keys = (self.admin_key, self.agent_key, self.webhook_secret, self.gateway_key)
            if any(len(key) < 32 or key.startswith("local-demo-") for key in keys) or len(set(keys)) != len(keys):
                raise RuntimeError("Hosted demo requires four distinct generated credentials of at least 32 characters")
            if not self.database_url.startswith(("postgres://", "postgresql://", "postgresql+psycopg://")):
                raise RuntimeError("Hosted demo requires persistent PostgreSQL")
            if not self.data_dir.is_absolute():
                raise RuntimeError("Hosted demo requires an absolute persistent document directory")
        self.data_dir.mkdir(parents=True, exist_ok=True)
