"""Stable per-job event ordering for events within the same second."""
from alembic import op
import sqlalchemy as sa

revision = "002_event_order"
down_revision = "696de9377913"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("job_events", sa.Column("sequence", sa.Integer(), nullable=False, server_default="1"))
    connection = op.get_bind()
    events = connection.execute(sa.text("SELECT id, job_id FROM job_events ORDER BY created_at, id")).all()
    counters = {}
    for event_id, job_id in events:
        counters[job_id] = counters.get(job_id, 0) + 1
        connection.execute(sa.text("UPDATE job_events SET sequence=:sequence WHERE id=:id"), {"sequence": counters[job_id], "id": event_id})


def downgrade():
    op.drop_column("job_events", "sequence")
