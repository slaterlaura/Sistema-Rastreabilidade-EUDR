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
