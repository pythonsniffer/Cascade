"""SQLModel engine + session (Backend Instructions §8)."""
from __future__ import annotations

import logging
from contextlib import contextmanager

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from backend.config.loader import Settings
import backend.store.models  # noqa: F401  (registers tables on SQLModel.metadata)

log = logging.getLogger("cascade.db")
_engine = None


def init_engine(settings: Settings):
    """Create the engine and tables. Postgres-ready: only the URL changes."""
    global _engine
    url = settings.database_url
    kwargs: dict = {"echo": False}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in url:
            kwargs["poolclass"] = StaticPool
    _engine = create_engine(url, **kwargs)
    SQLModel.metadata.create_all(_engine)
    log.info("database ready: %s", url)
    return _engine


def get_engine():
    if _engine is None:
        raise RuntimeError("database engine not initialised; call init_engine() at startup")
    return _engine


@contextmanager
def session_scope():
    """Commit on exit, keeping instances usable afterwards.

    expire_on_commit=False matters: the read helpers in repo.py return rows to the
    API layer, which touches their attributes after the session has closed.
    """
    with Session(get_engine(), expire_on_commit=False) as s:
        yield s
        s.commit()
