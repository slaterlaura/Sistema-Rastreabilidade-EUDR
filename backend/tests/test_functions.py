"""Ponte com o Azure Functions: a Function embrulha o FastAPI sem mudar rotas nem comportamento."""

import asyncio
import json
from pathlib import Path

import azure.functions as func

BACKEND = Path(__file__).resolve().parents[1]
PDF = b"%PDF-1.4\n\x00\xff\x10binario\n%%EOF"


def chamar(method, url, *, body=b"", headers=None):
    """Passa pelo mesmo AsgiMiddleware que o host do Functions usa em produção."""
    from app.main import app as fastapi_app

    req = func.HttpRequest(method=method, url=f"http://localhost:7071{url}", body=body, headers=headers or {})
    return asyncio.run(func.AsgiMiddleware(fastapi_app).handle_async(req))


def test_function_app_tem_uma_rota_catch_all_para_todos_os_metodos():
    import function_app

    funcoes = function_app.app.get_functions()
    assert len(funcoes) == 1
    ligacao = funcoes[0].get_bindings()[0]
    assert ligacao.route == "/{*route}"
    metodos = {m.value for m in ligacao.methods}
    assert {"GET", "POST", "PUT", "DELETE", "OPTIONS"} <= metodos  # OPTIONS: preflight de CORS
    assert ligacao.auth_level == func.AuthLevel.ANONYMOUS or str(ligacao.auth_level).endswith("ANONYMOUS")


def test_host_json_mantem_rotas_sem_prefixo_api():
    host = json.loads((BACKEND / "host.json").read_text())
    assert host["version"] == "2.0" and host["extensions"]["http"]["routePrefix"] == ""


def test_funcignore_nao_empacota_testes_scripts_nem_segredos():
    ignorados = (BACKEND / ".funcignore").read_text().split()
    for item in ("tests", "scripts", "alembic", ".venv", "local.settings.json", "requirements-dev.txt"):
        assert item in ignorados


def test_requirements_de_runtime_nao_trazem_pacotes_de_script_ou_teste():
    runtime = {l.split("[")[0].strip().lower() for l in (BACKEND / "requirements.txt").read_text().splitlines() if l and not l.startswith("#")}
    assert {"azure-functions", "azure-storage-blob", "azure-identity", "fastapi"} <= runtime
    assert not runtime & {"geopandas", "pyogrio", "pytest", "httpx"}


def test_health_e_docs_pela_function():
    r = chamar("GET", "/health")
    assert r.status_code == 200 and json.loads(r.get_body()) == {"status": "ok"}
    assert chamar("GET", "/openapi.json").status_code == 200


def test_preflight_de_cors_e_atendido_pelo_fastapi():
    r = chamar("OPTIONS", "/fazendas", headers={
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "authorization",
    })
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert chamar("OPTIONS", "/fazendas", headers={"Origin": "https://malicioso.example", "Access-Control-Request-Method": "GET"}).status_code == 400


def test_fluxo_autenticado_com_upload_binario_pela_function():
    corpo = json.dumps({"nome": "Mariana", "email": "mariana@exportadora.com", "senha": "senha-forte-123"}).encode()
    json_h = {"Content-Type": "application/json"}
    assert chamar("POST", "/auth/registrar", body=corpo, headers=json_h).status_code == 201
    login = chamar("POST", "/auth/login", body=json.dumps({"email": "mariana@exportadora.com", "senha": "senha-forte-123"}).encode(), headers=json_h)
    token = json.loads(login.get_body())["access_token"]
    auth = {"Authorization": f"Bearer {token}"}

    assert chamar("GET", "/fazendas").status_code == 401
    forn = chamar("POST", "/fornecedores", body=json.dumps({"nome": "Sítio Boa Vista", "documento": "529.982.247-25"}).encode(), headers={**json_h, **auth})
    assert forn.status_code == 201
    fid = json.loads(forn.get_body())["id"]

    limite = "----limite123"
    multipart = (
        f"--{limite}\r\nContent-Disposition: form-data; name=\"tipo\"\r\n\r\ncar\r\n"
        f"--{limite}\r\nContent-Disposition: form-data; name=\"arquivo\"; filename=\"car.pdf\"\r\nContent-Type: application/pdf\r\n\r\n"
    ).encode() + PDF + f"\r\n--{limite}--\r\n".encode()
    up = chamar("POST", f"/fornecedores/{fid}/documentos", body=multipart, headers={**auth, "Content-Type": f"multipart/form-data; boundary={limite}"})
    assert up.status_code == 201, up.get_body()
    doc = json.loads(up.get_body())
    assert doc["tamanho_bytes"] == len(PDF)

    baixado = chamar("GET", f"/documentos/{doc['id']}/arquivo", headers=auth)
    assert baixado.status_code == 200 and baixado.get_body() == PDF  # bytes idênticos pela ponte
