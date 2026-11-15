"""Fazendas de demonstração adotadas da camada de imóveis do CAR."""

import pytest
from sqlalchemy import select, text

from app.auth import gerar_hash
from app.database import SessionLocal, engine
from app.models import Embarque, Fazenda, Fornecedor, Usuario
from scripts import seed_imoveis
from scripts.seed import EMAIL
from tests.conftest import SUPRESSAO


@pytest.fixture
def imoveis_mg():
    """Três imóveis limpos (~18 ha cada, longe da supressão) e um em cima dela."""
    lon, lat, _ = SUPRESSAO
    posicoes = {
        "MG-3100104-A": (-49.50, -21.50), "MG-3100104-B": (-49.40, -21.50), "MG-3100104-C": (-49.30, -21.50),
        "MG-3100104-SUP": (lon + 0.001, lat + 0.001),
    }
    with engine.begin() as con:
        vid = con.execute(
            text("INSERT INTO imovel_versao (origem, uf, n_feicoes) VALUES ('SICAR','MG',4) RETURNING id")
        ).scalar_one()
        for cod, (x, y) in posicoes.items():
            con.execute(
                text(
                    "INSERT INTO imovel (cod_imovel, municipio, uf, area_ha, situacao, versao_id, geom) "
                    "VALUES (:c, 'ABADIA DOS DOURADOS', 'MG', 40, 'AT', :v, ST_MakeEnvelope(:x, :y, :x + 0.006, :y + 0.006, 4326))"
                ),
                {"c": cod, "v": vid, "x": x, "y": y},
            )


@pytest.fixture
def usuario_demo():
    with SessionLocal() as db:
        db.add(Usuario(nome="Mariana (demo)", email=EMAIL, senha_hash=gerar_hash("x-senha-teste")))
        db.commit()


def test_cria_aptas_bloqueada_e_embarque(camada, imoveis_mg, usuario_demo):
    novas = seed_imoveis.executar(["--ufs", "MG"])
    assert sorted(f.status for f in novas) == ["apta", "apta", "bloqueada"]
    with SessionLocal() as db:
        fazendas = db.scalars(select(Fazenda)).all()
        bloqueada = next(f for f in fazendas if f.status == "bloqueada")
        assert bloqueada.car_codigo == "MG-3100104-SUP" and bloqueada.area_sobreposta_m2 > 1000
        assert {f.car_codigo for f in fazendas if f.status == "apta"} == {"MG-3100104-A", "MG-3100104-B"}
        assert all(f.municipio == "Abadia dos Dourados" and f.uf == "MG" for f in fazendas)
        embarque = db.scalar(select(Embarque).where(Embarque.identificacao == "EMB-DEMO-002"))
        assert len(embarque.parcelas) == 2
        assert db.scalar(select(Fornecedor.nome)) == "Cooperativa Demo MG"


def test_rodar_de_novo_nao_duplica(camada, imoveis_mg, usuario_demo):
    seed_imoveis.executar(["--ufs", "MG"])
    assert seed_imoveis.executar(["--ufs", "MG"]) == []
    with SessionLocal() as db:
        assert len(db.scalars(select(Fazenda)).all()) == 3
        assert len(db.scalars(select(Fornecedor)).all()) == 1
        assert len(db.scalars(select(Embarque)).all()) == 1


def test_sem_usuario_demo_aborta(camada, imoveis_mg):
    with pytest.raises(SystemExit, match="seed.py"):
        seed_imoveis.executar(["--ufs", "MG"])


def test_cnpj_demo_tem_digitos_validos():
    assert seed_imoveis.cnpj_demo("112223330001") == "11222333000181"
