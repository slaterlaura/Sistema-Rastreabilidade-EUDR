"""Ponto de entrada do Azure Functions (modelo de programação Python v2).

Embrulha o FastAPI existente: cada requisição HTTP vira uma execução da Function e é servida pelo
mesmo `app.main:app` que roda com `uvicorn` no desenvolvimento. As rotas não mudam
(host.json define `routePrefix` vazio, então não existe o prefixo /api).

A autenticação do sistema é o JWT do próprio FastAPI; por isso a Function é anônima.
"""

import azure.functions as func

from app.main import app as fastapi_app

app = func.AsgiFunctionApp(app=fastapi_app, http_auth_level=func.AuthLevel.ANONYMOUS)
