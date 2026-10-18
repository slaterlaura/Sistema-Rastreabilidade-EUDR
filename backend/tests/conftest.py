"""Testes rodam num banco próprio (eudr_test) criado a partir do mesmo servidor do .env."""

import os
import re
import sys
from pathlib import Path

import psycopg2
import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))


def _url_teste() -> str:
    from dotenv import dotenv_values  # instalado junto com uvicorn[standard]

    url = os.environ.get("DATABASE_URL") or dotenv_values(BACKEND.parent / ".env")["DATABASE_URL"]
    return re.sub(r"/[^/?]+(\?|$)", r"/eudr_test\1", url, count=1)


URL_TESTE = _url_teste()
os.environ["DATABASE_URL"] = URL_TESTE
os.environ["STORAGE_DIR"] = str(BACKEND / "storage_teste")
os.environ.setdefault("TOLERANCIA_M2", "1000")


def _recriar_banco() -> None:
    admin = re.sub(r"/eudr_test(\?|$)", r"/postgres\1", URL_TESTE).replace("+psycopg2", "")
    con = psycopg2.connect(admin)
    con.autocommit = True
    cur = con.cursor()
    cur.execute("DROP DATABASE IF EXISTS eudr_test WITH (FORCE)")
    cur.execute("CREATE DATABASE eudr_test")
    con.close()


@pytest.fixture(scope="session", autouse=True)
def banco():
    _recriar_banco()
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    command.upgrade(cfg, "head")
    yield
    import shutil

    shutil.rmtree(BACKEND / "storage_teste", ignore_errors=True)


@pytest.fixture(autouse=True)
def limpar(banco):
    import shutil

    from sqlalchemy import text

    from app.database import engine

    shutil.rmtree(BACKEND / "storage_teste", ignore_errors=True)
    with engine.begin() as con:
        con.execute(
            text(
                "TRUNCATE usuario, fornecedor, fazenda, documento, camada_versao, camada_prodes, "
                "embarque, parcela, dossie RESTART IDENTITY CASCADE"
            )
        )
    yield


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


def _cadastrar(client, email, nome="Mariana"):
    client.post("/auth/registrar", json={"nome": nome, "email": email, "senha": "senha-forte-123"})
    token = client.post("/auth/login", json={"email": email, "senha": "senha-forte-123"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth(client):
    return _cadastrar(client, "mariana@exportadora.com")


@pytest.fixture
def auth_b(client):
    return _cadastrar(client, "outro@exportadora.com", "Outro")


def quadrado(lon, lat, lado):
    return {
        "type": "Polygon",
        "coordinates": [[[lon, lat], [lon + lado, lat], [lon + lado, lat + lado], [lon, lat + lado], [lon, lat]]],
    }


# Camada sintética: supressão de 2022 em [-50.00,-49.99] x [-21.00,-20.99] (~1 km²)
# e uma de 2019 (anterior ao corte) bem longe, que nunca pode bloquear.
SUPRESSAO = (-50.0, -21.0, 0.01)
ANTIGA_2019 = (-45.0, -15.0, 0.01)


@pytest.fixture
def camada():
    from sqlalchemy import text

    from app.database import engine

    with engine.begin() as con:
        vid = con.execute(
            text("INSERT INTO camada_versao (origem, bioma, uf, n_feicoes) VALUES ('PRODES','Teste','SP',2) RETURNING id")
        ).scalar_one()
        for (lon, lat, lado), ano in ((SUPRESSAO, 2022), (ANTIGA_2019, 2019)):
            poligono = (
                f"POLYGON(({lon} {lat},{lon+lado} {lat},{lon+lado} {lat+lado},{lon} {lat+lado},{lon} {lat}))"
            )
            con.execute(
                text("INSERT INTO camada_prodes (versao_id, geom, ano) VALUES (:v, ST_GeomFromText(:g, 4326), :a)"),
                {"v": vid, "g": poligono, "a": ano},
            )
    return vid


@pytest.fixture
def fornecedor(client, auth):
    r = client.post(
        "/fornecedores", json={"nome": "Sítio Boa Vista", "documento": "529.982.247-25"}, headers=auth
    )
    assert r.status_code == 201, r.text
    return r.json()
