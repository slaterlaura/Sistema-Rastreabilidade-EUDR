import json

from sqlalchemy import text

from tests.conftest import SUPRESSAO, quadrado


def nova_fazenda(client, auth, fornecedor, geometry, nome="Faz", **extra):
    r = client.post(
        "/fazendas",
        headers=auth,
        json={"fornecedor_id": fornecedor["id"], "nome": nome, "geometry": geometry, **extra},
    )
    assert r.status_code == 201, r.text
    return r.json()


LOTE = {
    "produto": "cafe_arabica_verde",
    "tipo_classificacao": "NY 2/3",
    "bebida": "Dura",
    "peneira": "17/18",
    "regiao_origem": "Cerrado Mineiro",
}


def novo_embarque(client, auth, identificacao="EMB-001", **lote):
    r = client.post(
        "/embarques",
        headers=auth,
        json={"identificacao": identificacao, "data_embarque": "2027-02-10", "destino": "Hamburgo, DE",
              **(lote or LOTE)},
    )
    assert r.status_code == 201, r.text
    return r.json()


def bloqueada(client, auth, fornecedor):
    lon, lat, _ = SUPRESSAO
    return nova_fazenda(client, auth, fornecedor, quadrado(lon + 0.002, lat + 0.002, 0.004), nome="Sobre desmatamento")


def parcelas(*pares):
    return {"parcelas": [{"fazenda_id": i, "quantidade_kg": q} for i, q in pares]}


def test_embarque_nasce_como_rascunho(client, auth):
    e = novo_embarque(client, auth)
    assert e["status"] == "rascunho" and e["parcelas"] == [] and e["dossie_id"] is None


def test_servidor_recusa_fazenda_bloqueada_e_nomeia_a_recusada(client, auth, fornecedor, camada):
    boa = nova_fazenda(client, auth, fornecedor, quadrado(-49.5, -21.5, 0.01), nome="Boa")
    ruim = bloqueada(client, auth, fornecedor)
    e = novo_embarque(client, auth)
    r = client.put(f"/embarques/{e['id']}/parcelas", headers=auth, json=parcelas((boa["id"], 100), (ruim["id"], 50)))
    assert r.status_code == 400
    assert "Sobre desmatamento" in r.json()["detail"] and f"id {ruim['id']}" in r.json()["detail"]
    assert "Boa" not in r.json()["detail"]
    assert client.get(f"/embarques/{e['id']}", headers=auth).json()["parcelas"] == []  # nada foi gravado


def test_compoe_embarque_com_aptas_e_soma_quantidades(client, auth, fornecedor, camada):
    a = nova_fazenda(client, auth, fornecedor, quadrado(-49.5, -21.5, 0.01), nome="Fazenda A")
    b = nova_fazenda(client, auth, fornecedor, quadrado(-49.3, -21.5, 0.01), nome="Fazenda B")
    e = novo_embarque(client, auth)
    r = client.put(f"/embarques/{e['id']}/parcelas", headers=auth, json=parcelas((a["id"], 1200.5), (b["id"], 800)))
    assert r.status_code == 200
    corpo = r.json()
    assert float(corpo["total_kg"]) == 2000.5 and {p["fazenda_nome"] for p in corpo["parcelas"]} == {"Fazenda A", "Fazenda B"}
    # PUT substitui a composição
    r = client.put(f"/embarques/{e['id']}/parcelas", headers=auth, json=parcelas((a["id"], 10)))
    assert len(r.json()["parcelas"]) == 1


def test_recusa_fazenda_repetida_quantidade_invalida_e_fazenda_alheia(client, auth, auth_b, fornecedor, camada):
    a = nova_fazenda(client, auth, fornecedor, quadrado(-49.5, -21.5, 0.01))
    e = novo_embarque(client, auth)
    url = f"/embarques/{e['id']}/parcelas"
    assert client.put(url, headers=auth, json=parcelas((a["id"], 1), (a["id"], 2))).status_code == 400
    assert client.put(url, headers=auth, json=parcelas((a["id"], 0))).status_code == 422
    assert client.put(url, headers=auth, json=parcelas((a["id"], -5))).status_code == 422
    assert client.put(url, headers=auth, json=parcelas((9999, 5))).status_code == 404
    eb = novo_embarque(client, auth_b, "EMB-B")
    assert client.put(f"/embarques/{eb['id']}/parcelas", headers=auth_b, json=parcelas((a["id"], 5))).status_code == 404


def test_fechar_gera_dossie_com_geojson_e_pdf(client, auth, fornecedor, camada):
    a = nova_fazenda(client, auth, fornecedor, quadrado(-49.5, -21.5, 0.01), nome="Sítio A", car_codigo="SP-A")
    e = novo_embarque(client, auth)
    client.put(f"/embarques/{e['id']}/parcelas", headers=auth, json=parcelas((a["id"], 1500)))
    r = client.post(f"/embarques/{e['id']}/fechar", headers=auth)
    assert r.status_code == 200, r.text
    fechado = r.json()
    assert fechado["status"] == "fechado" and fechado["fechado_em"] and fechado["dossie_id"]

    d = fechado["dossie_id"]
    assert [x["id"] for x in client.get("/dossies", headers=auth).json()] == [d]
    assert client.get("/dossies", headers=auth).json()[0]["retrato"] is None
    det = client.get(f"/dossies/{d}", headers=auth).json()
    assert det["embarque_identificacao"] == "EMB-001" and det["n_parcelas"] == 1
    assert det["retrato"]["parcelas"][0]["fazenda"]["car_codigo"] == "SP-A"
    assert det["retrato"]["camadas_referencia"][0]["id"] == camada

    gj = client.get(f"/dossies/{d}/geojson", headers=auth)
    assert gj.status_code == 200 and "attachment" in gj.headers["content-disposition"]
    colecao = json.loads(gj.content)
    assert colecao["type"] == "FeatureCollection" and colecao["features"][0]["properties"]["status"] == "apta"
    assert colecao["features"][0]["geometry"]["type"] == "Polygon"

    pdf = client.get(f"/dossies/{d}/pdf", headers=auth)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF") and len(pdf.content) > 1500
    assert pdf.headers["content-disposition"].startswith("attachment")


def test_dossie_e_retrato_congelado_nao_muda_com_novo_prodes(client, auth, fornecedor, camada):
    from app.database import engine

    a = nova_fazenda(client, auth, fornecedor, quadrado(-49.5, -21.5, 0.01), nome="Sítio A")
    e = novo_embarque(client, auth)
    client.put(f"/embarques/{e['id']}/parcelas", headers=auth, json=parcelas((a["id"], 1000)))
    d = client.post(f"/embarques/{e['id']}/fechar", headers=auth).json()["dossie_id"]
    antes = client.get(f"/dossies/{d}", headers=auth).json()["retrato"]
    geojson_antes = client.get(f"/dossies/{d}/geojson", headers=auth).content

    # nova camada marca a área como supressão recente e a fazenda é reverificada
    with engine.begin() as con:
        con.execute(text("INSERT INTO camada_prodes (versao_id, geom, ano) VALUES (:v, ST_GeomFromText('POLYGON((-49.51 -21.51,-49.48 -21.51,-49.48 -21.48,-49.51 -21.48,-49.51 -21.51))',4326), 2025)"), {"v": camada})
    client.post("/fazendas/reverificar", headers=auth)
    assert client.get(f"/fazendas/{a['id']}", headers=auth).json()["status"] == "bloqueada"

    depois = client.get(f"/dossies/{d}", headers=auth).json()["retrato"]
    assert depois == antes and depois["parcelas"][0]["fazenda"]["status"] == "apta"
    assert client.get(f"/dossies/{d}/geojson", headers=auth).content == geojson_antes


def test_fechamento_revalida_fazenda_que_ficou_bloqueada_depois_da_composicao(client, auth, fornecedor, camada):
    from app.database import engine

    a = nova_fazenda(client, auth, fornecedor, quadrado(-49.5, -21.5, 0.01), nome="Sítio A")
    e = novo_embarque(client, auth)
    client.put(f"/embarques/{e['id']}/parcelas", headers=auth, json=parcelas((a["id"], 1000)))
    with engine.begin() as con:
        con.execute(text("INSERT INTO camada_prodes (versao_id, geom, ano) VALUES (:v, ST_GeomFromText('POLYGON((-49.51 -21.51,-49.48 -21.51,-49.48 -21.48,-49.51 -21.48,-49.51 -21.51))',4326), 2025)"), {"v": camada})
    client.post("/fazendas/reverificar", headers=auth)
    r = client.post(f"/embarques/{e['id']}/fechar", headers=auth)
    assert r.status_code == 400 and "Sítio A" in r.json()["detail"]
    assert client.get(f"/embarques/{e['id']}", headers=auth).json()["status"] == "rascunho"
    assert client.get("/dossies", headers=auth).json() == []


def test_embarque_fechado_e_imutavel(client, auth, fornecedor, camada):
    a = nova_fazenda(client, auth, fornecedor, quadrado(-49.5, -21.5, 0.01))
    e = novo_embarque(client, auth)
    client.put(f"/embarques/{e['id']}/parcelas", headers=auth, json=parcelas((a["id"], 1000)))
    assert client.post(f"/embarques/{e['id']}/fechar", headers=auth).status_code == 200
    assert client.put(f"/embarques/{e['id']}/parcelas", headers=auth, json=parcelas((a["id"], 5))).status_code == 409
    assert client.put(f"/embarques/{e['id']}", headers=auth, json={"identificacao": "X", "data_embarque": "2027-01-01", "destino": "Rotterdam"}).status_code == 409
    assert client.delete(f"/embarques/{e['id']}", headers=auth).status_code == 409
    assert client.post(f"/embarques/{e['id']}/fechar", headers=auth).status_code == 409
    # fazenda usada em embarque não pode ser excluída
    assert client.delete(f"/fazendas/{a['id']}", headers=auth).status_code == 409


def test_nao_fecha_embarque_vazio(client, auth):
    e = novo_embarque(client, auth)
    r = client.post(f"/embarques/{e['id']}/fechar", headers=auth)
    assert r.status_code == 400 and "ao menos uma parcela" in r.json()["detail"]


def test_identificacao_duplicada_e_isolamento(client, auth, auth_b):
    novo_embarque(client, auth)
    r = client.post("/embarques", headers=auth, json={"identificacao": "EMB-001", "data_embarque": "2027-02-10", "destino": "Hamburgo"})
    assert r.status_code == 409
    e = novo_embarque(client, auth, "EMB-002")
    assert client.get(f"/embarques/{e['id']}", headers=auth_b).status_code == 404
    assert client.post(f"/embarques/{e['id']}/fechar", headers=auth_b).status_code == 404
    assert client.get("/embarques", headers=auth_b).json() == []


def test_dossie_de_outro_usuario_da_404(client, auth, auth_b, fornecedor, camada):
    a = nova_fazenda(client, auth, fornecedor, quadrado(-49.5, -21.5, 0.01))
    e = novo_embarque(client, auth)
    client.put(f"/embarques/{e['id']}/parcelas", headers=auth, json=parcelas((a["id"], 1000)))
    d = client.post(f"/embarques/{e['id']}/fechar", headers=auth).json()["dossie_id"]
    for sufixo in ("", "/geojson", "/pdf"):
        assert client.get(f"/dossies/{d}{sufixo}", headers=auth_b).status_code == 404
    assert client.get("/dossies", headers=auth_b).json() == []


def test_retrato_inclui_documentos_com_hash(client, auth, fornecedor, camada):
    a = nova_fazenda(client, auth, fornecedor, quadrado(-49.5, -21.5, 0.01))
    pdf = b"%PDF-1.4\n%%EOF"
    client.post(f"/fazendas/{a['id']}/documentos", headers=auth, files={"arquivo": ("car.pdf", pdf)}, data={"tipo": "car"})
    client.post(f"/fornecedores/{fornecedor['id']}/documentos", headers=auth, files={"arquivo": ("contrato.pdf", pdf)}, data={"tipo": "contrato"})
    e = novo_embarque(client, auth)
    client.put(f"/embarques/{e['id']}/parcelas", headers=auth, json=parcelas((a["id"], 1000)))
    d = client.post(f"/embarques/{e['id']}/fechar", headers=auth).json()["dossie_id"]
    p = client.get(f"/dossies/{d}", headers=auth).json()["retrato"]["parcelas"][0]
    assert [x["tipo"] for x in p["fazenda"]["documentos"]] == ["car"]
    assert [x["tipo"] for x in p["fornecedor"]["documentos"]] == ["contrato"]
    assert len(p["fazenda"]["documentos"][0]["sha256"]) == 64


def test_produto_e_especificacao_do_lote_vao_para_o_retrato_e_o_pdf(client, auth, fornecedor, camada):
    from app.services.dossie import descrever_lote

    e = novo_embarque(client, auth)
    assert e["produto"] == {"codigo": "cafe_arabica_verde", "descricao": "Café arábica verde (cru, em grão)",
                            "codigo_sh": "0901.11"}
    assert (e["tipo_classificacao"], e["bebida"], e["peneira"], e["regiao_origem"]) == (
        "NY 2/3", "Dura", "17/18", "Cerrado Mineiro")

    f = nova_fazenda(client, auth, fornecedor, quadrado(-49.5, -21.5, 0.01))
    client.put(f"/embarques/{e['id']}/parcelas", headers=auth, json=parcelas((f["id"], 100000)))
    d = client.post(f"/embarques/{e['id']}/fechar", headers=auth).json()["dossie_id"]
    retrato = client.get(f"/dossies/{d}", headers=auth).json()["retrato"]
    assert retrato["versao_retrato"] == 2
    assert retrato["embarque"]["produto"]["codigo_sh"] == "0901.11"
    assert retrato["embarque"]["especificacao"]["peneira"] == "17/18"
    assert descrever_lote(retrato["embarque"]) == (
        "Café arábica verde (cru, em grão) (SH 0901.11)",
        "tipo NY 2/3 · bebida dura · peneira 17/18 · origem Cerrado Mineiro",
    )
    geojson = json.loads(client.get(f"/dossies/{d}/geojson", headers=auth).content)
    assert geojson["embarque"]["produto"]["codigo"] == "cafe_arabica_verde"


def test_produto_e_exigido_para_fechar_mas_nao_no_rascunho(client, auth, fornecedor, camada):
    e = novo_embarque(client, auth, produto=None)
    assert e["produto"] is None and e["tipo_classificacao"] is None
    f = nova_fazenda(client, auth, fornecedor, quadrado(-49.5, -21.5, 0.01))
    client.put(f"/embarques/{e['id']}/parcelas", headers=auth, json=parcelas((f["id"], 500)))
    r = client.post(f"/embarques/{e['id']}/fechar", headers=auth)
    assert r.status_code == 400 and "produto" in r.json()["detail"]

    corpo = {"identificacao": "EMB-001", "data_embarque": "2027-02-10", "destino": "Hamburgo, DE",
             "produto": "cafe_conilon_verde", "bebida": "  "}
    atualizado = client.put(f"/embarques/{e['id']}", headers=auth, json=corpo).json()
    assert atualizado["produto"]["codigo"] == "cafe_conilon_verde" and atualizado["bebida"] is None
    assert client.post(f"/embarques/{e['id']}/fechar", headers=auth).status_code == 200


def test_produto_fora_da_lista_e_recusado(client, auth):
    r = client.post("/embarques", headers=auth, json={"identificacao": "X", "data_embarque": "2027-02-10",
                                                       "destino": "Hamburgo", "produto": "soja"})
    assert r.status_code == 422 and "produto" in r.text


def test_retrato_antigo_sem_produto_ainda_gera_texto():
    from app.services.dossie import descrever_lote

    assert descrever_lote({"identificacao": "EMB-ANTIGO"}) == ("não informado", "não informada")
