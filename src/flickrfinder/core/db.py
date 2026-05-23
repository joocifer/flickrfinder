from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from flickrfinder.config import Config
from flickrfinder.core.models import Base

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine(cfg: Config) -> Engine:
    global _engine
    if _engine is None:
        url = f"sqlite:///{cfg.db_path}"
        _engine = create_engine(url, future=True)
    return _engine


def init_db(cfg: Config) -> None:
    Base.metadata.create_all(get_engine(cfg))


def session_factory(cfg: Config) -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(cfg), expire_on_commit=False)
    return _SessionLocal


@contextmanager
def session_scope(cfg: Config) -> Iterator[Session]:
    sf = session_factory(cfg)
    s = sf()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()
