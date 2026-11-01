"""Camada comum de imóveis do CAR: visível para todos os usuários, adotável como fazenda."""

import pytest
from sqlalchemy import text

from app.database import engine
from tests.conftest import SUPRESSAO, quadrado

# Um imóvel sobre a supressão sintética (2022) e outro longe dela
SOBRE = "MG-3100104-SOBRE"
LIMPO = "MG-3100104-LIMPO"


@pytest.fixture
def imoveis():
    lon, lat, _ = SUPRESSAO
    with engine.begin() as con:
        vid = con.execute(
            text("INSERT INTO imovel_versao (origem, uf, n_feicoes) VALUES ('SICAR','MG',2) RETURNING id")
        ).scalar_one()
        for cod, (x, y) in ((SOBRE, (lon + 0.002, lat + 0.002)), (LIMPO, (-49.5, -21.5))):
            con.execute(
                text(
                    "INSERT INTO imovel (cod_imovel, municipio, uf, area_ha, situacao, versao_id, geom) "
                    "VALUES (:c, 'Abadia', 'MG', 18.4, 'AT', :v, ST_MakeEnvelope(:x, :y, :x + 0.004, :y + 0.004, 4326))"
                ),
                {"c": cod, "v": vid, "x": x, "y": y},
            )
    return vid


def test_imoveis_do_recorte_aparecem_para_qualquer_usuario(client, auth, auth_b, imoveis):
    lon, lat, _ = SUPRESSAO
    url = f"/imoveis?bbox={lon - 0.1},{lat - 0.1},{lon + 0.1},{lat + 0.1}"
    for cabecalho in (auth, auth_b):  # camada comum: os dois veem o mesmo
        r = client.get(url, headers=cabecalho)
        assert r.status_code == 200
        props = [f["properties"] for f in r.json()["features"]]
        assert [p["cod_imovel"] for p in props] == [SOBRE]
        assert props[0]["uf"] == "MG" and props[0]["situacao"] == "AT"
    assert "max-age" in r.headers["cache-control"]


def test_recorte_grande_invalido_e_sem_login(client, auth, imoveis):
    assert client.get("/imoveis?bbox=-50,-22,-48,-20", headers=auth).status_code == 400
    assert client.get("/imoveis?bbox=a,b,c,d", headers=auth).status_code == 400
    assert client.get("/imoveis?bbox=-50.1,-21.1,-49.9,-20.9").status_code == 401


def test_detalhe_devolve_geometria_completa(client, auth, imoveis):
    r = client.get(f"/imoveis/{SOBRE}", headers=auth)
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["cod_imovel"] == SOBRE and corpo["area_ha"] == 18.4 and corpo["geometry"]["type"] == "Polygon"
    assert client.get("/imoveis/XX-0000000-NAOEXISTE", headers=auth).status_code == 404


def test_adotar_imovel_cria_fazenda_verificada(client, auth, auth_b, fornecedor, camada, imoveis):
    """O fluxo do frontend: pega o imóvel e cadastra como fazenda; a verificação (R1) roda ao salvar."""
    for cod, esperado in ((SOBRE, "bloqueada"), (LIMPO, "apta")):
        im = client.get(f"/imoveis/{cod}", headers=auth).json()
        r = client.post("/fazendas", headers=auth, json={
            "fornecedor_id": fornecedor["id"], "nome": f"Imóvel {cod[-5:]}", "car_codigo": im["cod_imovel"],
            "municipio": im["municipio"], "uf": im["uf"], "area_declarada_ha": im["area_ha"], "geometry": im["geometry"],
        })
        assert r.status_code == 201, r.text
        assert r.json()["status"] == esperado
    # adotar de novo o mesmo CAR na mesma conta é recusado
    im = client.get(f"/imoveis/{LIMPO}", headers=auth).json()
    r = client.post("/fazendas", headers=auth, json={"fornecedor_id": fornecedor["id"], "nome": "Dup", "car_codigo": LIMPO, "geometry": im["geometry"]})
    assert r.status_code == 409
    # a fazenda adotada é de quem adotou; o imóvel continua na camada comum
    assert client.get("/fazendas", headers=auth_b).json() == []
    assert len(client.get(f"/imoveis/{LIMPO}", headers=auth_b).json()["geometry"]["coordinates"][0]) == 5


def test_versao_da_camada_inclui_os_imoveis(client, auth, imoveis):
    assert client.get("/camada/versao", headers=auth).json()["imoveis_versao"] == imoveis
