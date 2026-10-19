from tests.conftest import ANTIGA_2019, SUPRESSAO, quadrado


def criar(client, auth, fornecedor, geometry, **extra):
    corpo = {"fornecedor_id": fornecedor["id"], "nome": "Fazenda Teste", "geometry": geometry, **extra}
    return client.post("/fazendas", json=corpo, headers=auth)


def test_fazenda_fora_da_supressao_fica_apta(client, auth, fornecedor, camada):
    r = criar(client, auth, fornecedor, quadrado(-49.5, -21.5, 0.01))
    assert r.status_code == 201, r.text
    f = r.json()
    assert f["status"] == "apta" and float(f["area_sobreposta_m2"]) == 0
    assert f["verificada_em"] and f["camada_versao_id"] == camada


def test_fazenda_sobre_supressao_fica_bloqueada_e_area_em_m2(client, auth, fornecedor, camada):
    lon, lat, lado = SUPRESSAO
    f = criar(client, auth, fornecedor, quadrado(lon + 0.002, lat + 0.002, 0.004)).json()
    assert f["status"] == "bloqueada"
    # 0,004° ≈ 443 m (lat) x 416 m (lon a 21°S) ≈ 184.000 m²; ~0,0003 indicaria o cast ::geography ausente
    assert 175_000 < float(f["area_sobreposta_m2"]) < 195_000


def test_sobreposicao_abaixo_da_tolerancia_nao_bloqueia(client, auth, fornecedor, camada):
    lon, lat, _ = SUPRESSAO
    # borda de ~0,0001° x 0,0001° (~120 m²) invadindo a supressão
    geom = {
        "type": "Polygon",
        "coordinates": [[[lon - 0.01, lat - 0.01], [lon + 0.0001, lat - 0.01], [lon + 0.0001, lat + 0.0001],
                         [lon - 0.01, lat + 0.0001], [lon - 0.01, lat - 0.01]]],
    }
    f = criar(client, auth, fornecedor, geom).json()
    assert f["status"] == "apta"
    assert 0 < float(f["area_sobreposta_m2"]) < 1000


def test_supressao_anterior_ao_corte_nao_bloqueia(client, auth, fornecedor, camada):
    lon, lat, lado = ANTIGA_2019
    f = criar(client, auth, fornecedor, quadrado(lon, lat, lado)).json()
    assert f["status"] == "apta"


def test_ponto_dentro_da_supressao_bloqueia(client, auth, fornecedor, camada):
    lon, lat, lado = SUPRESSAO
    ponto = {"type": "Point", "coordinates": [lon + lado / 2, lat + lado / 2]}
    f = criar(client, auth, fornecedor, ponto, area_declarada_ha=2).json()
    assert f["status"] == "bloqueada" and float(f["area_sobreposta_m2"]) == 0


def test_ponto_fora_da_supressao_fica_apto(client, auth, fornecedor, camada):
    f = criar(client, auth, fornecedor, {"type": "Point", "coordinates": [-49.0, -22.0]}, area_declarada_ha=3).json()
    assert f["status"] == "apta"


def test_ponto_acima_de_4_ha_e_recusado(client, auth, fornecedor, camada):
    r = criar(client, auth, fornecedor, {"type": "Point", "coordinates": [-49.0, -22.0]}, area_declarada_ha=5)
    assert r.status_code == 400 and "4 ha" in r.json()["detail"]


def test_ponto_sem_area_declarada_e_recusado(client, auth, fornecedor, camada):
    r = criar(client, auth, fornecedor, {"type": "Point", "coordinates": [-49.0, -22.0]})
    assert r.status_code == 400


def test_geometria_de_linha_e_recusada(client, auth, fornecedor, camada):
    r = criar(client, auth, fornecedor, {"type": "LineString", "coordinates": [[0, 0], [1, 1]]})
    assert r.status_code == 400


def test_poligono_com_area_zero_e_recusado(client, auth, fornecedor, camada):
    r = criar(client, auth, fornecedor, {"type": "Polygon", "coordinates": [[[-49, -21], [-49, -21], [-49, -21], [-49, -21]]]})
    assert r.status_code == 400


def test_area_acima_de_100_mil_ha_e_recusada(client, auth, fornecedor, camada):
    r = criar(client, auth, fornecedor, quadrado(-50, -22, 2))  # ~ 4,7 milhões de ha
    assert r.status_code == 400 and "100000" in r.json()["detail"]


def test_poligono_com_autointerseccao_e_reparado(client, auth, fornecedor, camada):
    gravata = {"type": "Polygon", "coordinates": [[[-49.5, -21.5], [-49.49, -21.49], [-49.49, -21.5], [-49.5, -21.49], [-49.5, -21.5]]]}
    r = criar(client, auth, fornecedor, gravata)
    assert r.status_code == 201, r.text


def test_sem_camada_carregada_recusa_em_vez_de_aprovar(client, auth, fornecedor):
    r = criar(client, auth, fornecedor, quadrado(-49.5, -21.5, 0.01))
    assert r.status_code == 503
    assert client.get("/fazendas", headers=auth).json() == []  # nada ficou salvo sem verificação (R1)


def test_alterar_geometria_reverifica(client, auth, fornecedor, camada):
    lon, lat, lado = SUPRESSAO
    f = criar(client, auth, fornecedor, quadrado(-49.5, -21.5, 0.01)).json()
    assert f["status"] == "apta"
    r = client.put(f"/fazendas/{f['id']}", json={"geometry": quadrado(lon + 0.002, lat + 0.002, 0.004)}, headers=auth)
    assert r.status_code == 200 and r.json()["status"] == "bloqueada"
    r = client.put(f"/fazendas/{f['id']}", json={"nome": "Outro nome"}, headers=auth)
    assert r.json()["status"] == "bloqueada" and r.json()["nome"] == "Outro nome"


def test_reverificar_detecta_camada_atualizada(client, auth, fornecedor, camada):
    from sqlalchemy import text

    from app.database import engine

    f = criar(client, auth, fornecedor, quadrado(-49.5, -21.5, 0.01)).json()
    with engine.begin() as con:
        con.execute(text("INSERT INTO camada_prodes (versao_id, geom, ano) VALUES (:v, ST_GeomFromText('POLYGON((-49.51 -21.51,-49.48 -21.51,-49.48 -21.48,-49.51 -21.48,-49.51 -21.51))',4326), 2024)"), {"v": camada})
    r = client.post("/fazendas/reverificar", headers=auth).json()
    assert r["mudaram_de_status"][0]["para"] == "bloqueada"
    assert client.get(f"/fazendas/{f['id']}", headers=auth).json()["status"] == "bloqueada"


def test_car_duplicado_da_conflito(client, auth, fornecedor, camada):
    assert criar(client, auth, fornecedor, quadrado(-49.5, -21.5, 0.01), car_codigo="SP-1").status_code == 201
    r = criar(client, auth, fornecedor, quadrado(-49.4, -21.4, 0.01), car_codigo="SP-1")
    assert r.status_code == 409 and "CAR" in r.json()["detail"]


def test_isolamento_entre_usuarios(client, auth, auth_b, fornecedor, camada):
    f = criar(client, auth, fornecedor, quadrado(-49.5, -21.5, 0.01)).json()
    assert client.get(f"/fazendas/{f['id']}", headers=auth_b).status_code == 404
    assert client.get(f"/fornecedores/{fornecedor['id']}", headers=auth_b).status_code == 404
    assert client.get("/fazendas", headers=auth_b).json() == []
    r = client.post("/fazendas", json={"fornecedor_id": fornecedor["id"], "nome": "Invasora", "geometry": quadrado(-49.5, -21.5, 0.01)}, headers=auth_b)
    assert r.status_code == 404
    assert client.delete(f"/fazendas/{f['id']}", headers=auth_b).status_code == 404


def test_sem_token_da_401(client):
    assert client.get("/fazendas").status_code == 401


def test_importar_geojson_e_tudo_ou_nada(client, auth, fornecedor, camada):
    lon, lat, lado = SUPRESSAO
    bom = {"type": "Feature", "properties": {"cod_imovel": "SP-A", "municipio": "X", "num_area": 10}, "geometry": quadrado(-49.5, -21.5, 0.01)}
    sobre = {"type": "Feature", "properties": {"cod_imovel": "SP-B"}, "geometry": quadrado(lon + 0.002, lat + 0.002, 0.004)}
    ok = client.post("/fazendas/import-geojson", json={"fornecedor_id": fornecedor["id"], "geojson": {"type": "FeatureCollection", "features": [bom, sobre]}}, headers=auth)
    assert ok.status_code == 201 and ok.json()["resumo"] == {"apta": 1, "bloqueada": 1}

    ruim = {"type": "Feature", "properties": {"cod_imovel": "SP-C"}, "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]}}
    novo = {"type": "Feature", "properties": {"cod_imovel": "SP-D"}, "geometry": quadrado(-49.0, -21.0, 0.01)}
    r = client.post("/fazendas/import-geojson", json={"fornecedor_id": fornecedor["id"], "geojson": {"type": "FeatureCollection", "features": [novo, ruim]}}, headers=auth)
    assert r.status_code == 400 and "Feição 1" in r.json()["detail"]
    assert len(client.get("/fazendas", headers=auth).json()) == 2  # a feição boa da 2ª tentativa não ficou


def test_cpf_invalido_e_duplicado(client, auth, fornecedor):
    assert client.post("/fornecedores", json={"nome": "Fulano", "documento": "111.111.111-11"}, headers=auth).status_code == 422
    r = client.post("/fornecedores", json={"nome": "Dup", "documento": "52998224725"}, headers=auth)
    assert r.status_code == 409


def test_nao_exclui_fornecedor_com_fazenda(client, auth, fornecedor, camada):
    criar(client, auth, fornecedor, quadrado(-49.5, -21.5, 0.01))
    assert client.delete(f"/fornecedores/{fornecedor['id']}", headers=auth).status_code == 409
