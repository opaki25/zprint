# Demo seed

Run python -m zprint.seed after alembic upgrade head. The idempotent seed creates ST001, one simulated B/W duplex A4 printer, a station agent and both illustrative price schedules at version 1. It does not create paid jobs, successful payments or a fake ready reading. The agent must heartbeat before payment is allowed.
