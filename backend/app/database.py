from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(
    settings.database_url,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=10,
    pool_recycle=300,  # o Azure derruba conexões ociosas
    pool_pre_ping=True,
    # Sem isso, banco inacessível (firewall) deixa a requisição pendurada até o timeout da Function,
    # gastando a cota de GB-s; com 10 s ela falha rápido e /health/db responde "unreachable".
    connect_args={"connect_timeout": 10},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
