import os
from alembic import context
from sqlalchemy import create_engine
from zprint.models import Base
from zprint.db import normalize_database_url

url = normalize_database_url(os.getenv("DATABASE_URL", context.config.get_main_option("sqlalchemy.url")))
if context.is_offline_mode():
    context.configure(url=url, target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()
