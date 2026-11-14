"""O usuário de banco "carga" (infra/papel-carga.sql) mexe só nas camadas de referência."""

import re
import secrets
from pathlib import Path

import psycopg2
import pytest
from sqlalchemy import text

from app.database import engine
from tests.conftest import URL_TESTE

SQL = (Path(__file__).resolve().parents[2] / "infra" / "papel-carga.sql").read_text()


@pytest.fixture
def conexao_carga():
    senha = secrets.token_hex(12)
    with engine.begin() as con:
        con.execute(text(SQL))
        con.execute(text(f"ALTER ROLE carga PASSWORD '{senha}'"))
    url = re.sub(r"//[^@]+@", f"//carga:{senha}@", URL_TESTE).replace("+psycopg2", "")
    con = psycopg2.connect(url)
    yield con
    con.close()
    with engine.begin() as admin:
        admin.execute(text("ALTER ROLE carga PASSWORD NULL"))  # sem senha, ninguém entra


def test_carga_consegue_gravar_imoveis_e_prodes(conexao_carga):
    with conexao_carga.cursor() as cur:
        cur.execute("INSERT INTO imovel_versao (origem, n_feicoes) VALUES ('SICAR', 1) RETURNING id")
        vid = cur.fetchone()[0]
        cur.execute("CREATE TEMP TABLE _t (cod text) ON COMMIT DROP")  # o script de carga usa tabela temporária
        cur.execute(
            "INSERT INTO imovel (cod_imovel, versao_id, geom) VALUES ('SP-1-A', %s, "
            "ST_MakeEnvelope(-47,-21,-46.99,-20.99,4326)) ON CONFLICT (cod_imovel) DO UPDATE SET versao_id = EXCLUDED.versao_id",
            (vid,),
        )
        cur.execute("INSERT INTO camada_versao (origem, bioma, n_feicoes) VALUES ('PRODES','Cerrado',0) RETURNING id")
        cur.execute("DELETE FROM camada_prodes WHERE versao_id = -1")
    conexao_carga.commit()


@pytest.mark.parametrize("tabela", ["usuario", "fornecedor", "fazenda", "documento", "embarque", "parcela", "dossie"])
def test_carga_nao_le_dados_dos_exportadores(conexao_carga, tabela):
    with conexao_carga.cursor() as cur:
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            cur.execute(f"SELECT 1 FROM {tabela} LIMIT 1")
    conexao_carga.rollback()


def test_carga_nao_altera_estrutura(conexao_carga):
    with conexao_carga.cursor() as cur:
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            cur.execute("DROP TABLE imovel")
    conexao_carga.rollback()
