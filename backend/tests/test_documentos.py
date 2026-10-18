from pathlib import Path

from tests.conftest import quadrado

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def enviar(client, auth, url, conteudo=PDF, nome="car.pdf", tipo="car", **extra):
    return client.post(url, headers=auth, files={"arquivo": (nome, conteudo)}, data={"tipo": tipo, **extra})


def test_anexa_lista_baixa_e_exclui_documento_do_fornecedor(client, auth, fornecedor):
    r = enviar(client, auth, f"/fornecedores/{fornecedor['id']}/documentos", validade="2027-05-01")
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["tipo"] == "car" and doc["content_type"] == "application/pdf" and len(doc["sha256"]) == 64
    assert doc["validade"] == "2027-05-01"

    assert len(client.get(f"/fornecedores/{fornecedor['id']}/documentos", headers=auth).json()) == 1
    baixado = client.get(f"/documentos/{doc['id']}/arquivo", headers=auth)
    assert baixado.status_code == 200 and baixado.content == PDF
    assert "attachment" in baixado.headers["content-disposition"]

    assert client.delete(f"/documentos/{doc['id']}", headers=auth).status_code == 204
    assert client.get(f"/documentos/{doc['id']}/arquivo", headers=auth).status_code == 404


def test_anexa_documento_a_fazenda(client, auth, fornecedor, camada):
    f = client.post("/fazendas", headers=auth, json={"fornecedor_id": fornecedor["id"], "nome": "Faz", "geometry": quadrado(-49.5, -21.5, 0.01)}).json()
    r = enviar(client, auth, f"/fazendas/{f['id']}/documentos", PNG, "matricula.png", "matricula")
    assert r.status_code == 201 and r.json()["fazenda_id"] == f["id"] and r.json()["content_type"] == "image/png"


def test_rejeita_formato_pelo_conteudo_e_nao_pelo_nome(client, auth, fornecedor):
    r = enviar(client, auth, f"/fornecedores/{fornecedor['id']}/documentos", b"MZ executavel", "virus.pdf")
    assert r.status_code == 400 and "PDF, PNG ou JPG" in r.json()["detail"]


def test_rejeita_tipo_invalido_e_arquivo_vazio_e_grande(client, auth, fornecedor):
    url = f"/fornecedores/{fornecedor['id']}/documentos"
    assert enviar(client, auth, url, tipo="xyz").status_code == 422
    assert enviar(client, auth, url, b"").status_code == 400
    assert enviar(client, auth, url, PDF + b"0" * (11 * 1024 * 1024)).status_code == 413


def test_nome_de_arquivo_nao_escapa_do_storage(client, auth, fornecedor):
    r = enviar(client, auth, f"/fornecedores/{fornecedor['id']}/documentos", nome="../../etc/passwd.pdf")
    assert r.status_code == 201 and r.json()["nome_arquivo"] == "passwd.pdf"


def test_documento_de_outro_usuario_da_404(client, auth, auth_b, fornecedor):
    doc = enviar(client, auth, f"/fornecedores/{fornecedor['id']}/documentos").json()
    assert client.get(f"/documentos/{doc['id']}/arquivo", headers=auth_b).status_code == 404
    assert client.delete(f"/documentos/{doc['id']}", headers=auth_b).status_code == 404
    assert enviar(client, auth_b, f"/fornecedores/{fornecedor['id']}/documentos").status_code == 404


def test_excluir_fazenda_remove_os_arquivos(client, auth, fornecedor, camada):
    from app.config import settings

    f = client.post("/fazendas", headers=auth, json={"fornecedor_id": fornecedor["id"], "nome": "Faz", "geometry": quadrado(-49.5, -21.5, 0.01)}).json()
    doc = enviar(client, auth, f"/fazendas/{f['id']}/documentos").json()
    assert any(Path(settings.storage_dir).rglob("*.pdf"))
    assert client.delete(f"/fazendas/{f['id']}", headers=auth).status_code == 204
    assert client.get(f"/fazendas/{f['id']}/documentos", headers=auth).status_code == 404
    assert not any(Path(settings.storage_dir).rglob("*.pdf"))
