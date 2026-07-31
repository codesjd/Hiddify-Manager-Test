import logging
from logging.config import fileConfig
from flask import current_app
from alembic import context
import os

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

logger = logging.getLogger('alembic.env')

def get_engine():
    try:
        from hiddifypanel.database import db
        return db.engine
    except RuntimeError:
        return None
    except Exception as e:
        logger.warning(f"Failed to get engine from app context: {e}")
        return None

def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=get_metadata(),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    connectable = get_engine()
    if connectable is None:
        from sqlalchemy import create_engine
        url = config.get_main_option("sqlalchemy.url")
        connectable = create_engine(url)

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=get_metadata()
        )
        with context.begin_transaction():
            context.run_migrations()

def get_metadata():
    try:
        from hiddifypanel.database import db
        return db.metadata
    except Exception as e:
        logger.error(e)
        return None

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
