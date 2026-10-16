import os

from sqlalchemy import create_engine, text


DATABASE_URL = (os.getenv("DATABASE_URL") or "").strip()
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

engine = None
if DATABASE_URL:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        future=True,
        connect_args={"connect_timeout": 5},
    )


def check_db_connection() -> bool:
    if engine is None:
        return False

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def ensure_eudr_schema() -> None:
    if engine is None:
        return

    ddl = """
    CREATE EXTENSION IF NOT EXISTS postgis;
    CREATE SCHEMA IF NOT EXISTS eudr;

    CREATE TABLE IF NOT EXISTS eudr.fornecedor (
        id BIGSERIAL PRIMARY KEY,
        nome TEXT NOT NULL,
        cpf_cnpj VARCHAR(20) NOT NULL UNIQUE,
        car_codigo TEXT,
        criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS eudr.camada_prodes (
        id BIGSERIAL PRIMARY KEY,
        fonte TEXT DEFAULT 'PRODES',
        estado CHAR(2),
        ano INTEGER NOT NULL,
        class_name TEXT,
        area_km DOUBLE PRECISION,
        geom geometry(MultiPolygon, 4326) NOT NULL,
        criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS eudr.fazenda (
        id BIGSERIAL PRIMARY KEY,
        fornecedor_id BIGINT NOT NULL REFERENCES eudr.fornecedor(id) ON DELETE RESTRICT,
        codigo_externo TEXT UNIQUE,
        nome TEXT,
        municipio TEXT,
        area_ha DOUBLE PRECISION,
        status_conformidade TEXT NOT NULL DEFAULT 'pendente'
            CHECK (status_conformidade IN ('pendente', 'apta', 'bloqueada')),
        area_sobreposta_m2 NUMERIC(18,2) NOT NULL DEFAULT 0,
        geom geometry(MultiPolygon, 4326) NOT NULL,
        criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS eudr.embarque (
        id BIGSERIAL PRIMARY KEY,
        identificacao TEXT NOT NULL UNIQUE,
        data_embarque DATE NOT NULL,
        destino TEXT NOT NULL,
        criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS eudr.embarque_fazenda (
        embarque_id BIGINT NOT NULL REFERENCES eudr.embarque(id) ON DELETE CASCADE,
        fazenda_id BIGINT NOT NULL REFERENCES eudr.fazenda(id) ON DELETE RESTRICT,
        criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (embarque_id, fazenda_id)
    );

    CREATE INDEX IF NOT EXISTS idx_camada_prodes_geom_gist
        ON eudr.camada_prodes USING GIST (geom);
    CREATE INDEX IF NOT EXISTS idx_fazenda_geom_gist
        ON eudr.fazenda USING GIST (geom);
    CREATE INDEX IF NOT EXISTS idx_fazenda_status
        ON eudr.fazenda (status_conformidade);
    CREATE INDEX IF NOT EXISTS idx_fazenda_fornecedor
        ON eudr.fazenda (fornecedor_id);
    """
    with engine.begin() as conn:
        conn.execute(text(ddl))