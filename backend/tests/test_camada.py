from tests.conftest import ANTIGA_2019, SUPRESSAO


def test_devolve_supressao_pos_corte_no_recorte(client, auth, camada):
    lon, lat, lado = SUPRESSAO
    r = client.get(f"/camada/prodes?bbox={lon - 0.1},{lat - 0.1},{lon + 0.1},{lat + 0.1}", headers=auth)
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["type"] == "FeatureCollection" and not corpo["truncado"]
    assert [f["properties"]["ano"] for f in corpo["features"]] == [2022]
    assert corpo["features"][0]["geometry"]["type"] == "Polygon"
    assert "max-age" in r.headers["cache-control"]


def test_supressao_anterior_ao_corte_nao_aparece(client, auth, camada):
    lon, lat, lado = ANTIGA_2019
    r = client.get(f"/camada/prodes?bbox={lon - 0.1},{lat - 0.1},{lon + 0.1},{lat + 0.1}", headers=auth)
    assert r.json()["features"] == []


def test_recorte_grande_ou_invalido_e_recusado(client, auth, camada):
    assert client.get("/camada/prodes?bbox=-55,-25,-44,-19", headers=auth).status_code == 400
    assert client.get("/camada/prodes?bbox=a,b,c,d", headers=auth).status_code == 400
    assert client.get("/camada/prodes?bbox=-49,-21,-50,-20", headers=auth).status_code == 400


def test_exige_login(client, camada):
    assert client.get("/camada/prodes?bbox=-50.1,-21.1,-49.9,-20.9").status_code == 401


def test_versao_da_camada_muda_a_cada_carga(client, auth, camada):
    from sqlalchemy import text

    from app.database import engine

    r = client.get("/camada/versao", headers=auth)
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    antes = r.json()
    assert antes["versao"] == camada and antes["biomas"] == ["Teste"]

    with engine.begin() as con:
        nova = con.execute(
            text("INSERT INTO camada_versao (origem, bioma, n_feicoes) VALUES ('PRODES','Cerrado',1) RETURNING id")
        ).scalar_one()
        con.execute(
            text("INSERT INTO camada_prodes (versao_id, geom, ano) VALUES (:v, ST_GeomFromText('POLYGON((-47 -15,-46.99 -15,-46.99 -14.99,-47 -14.99,-47 -15))',4326), 2023)"),
            {"v": nova},
        )
    depois = client.get("/camada/versao", headers=auth).json()
    assert depois["versao"] == nova and depois["biomas"] == ["Cerrado", "Teste"]


def test_versao_sem_camada_carregada(client, auth):
    assert client.get("/camada/versao", headers=auth).json() == {"versao": None, "atualizada_em": None, "biomas": []}
