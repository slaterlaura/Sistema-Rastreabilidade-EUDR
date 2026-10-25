from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import settings
from app.database import engine
from app.routers import auth, camada, documentos, dossies, embarques, fazendas, fornecedores

app = FastAPI(title="OrigemCheck — Rastreabilidade de Origem (EUDR)", version="0.3.0")

# CORS configurado só aqui (ativar também no painel do Azure duplica os cabeçalhos)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origens.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # O frontend (outra origem) manda Authorization, então cada GET vem precedido de um OPTIONS,
    # e no Functions cada um é uma execução. Com o cache do preflight o navegador pergunta uma vez
    # a cada 2 h por rota (o Chrome não aceita mais que isso).
    max_age=7200,
)

app.include_router(auth.router)
app.include_router(fornecedores.router)
app.include_router(fazendas.router)
app.include_router(documentos.router)
app.include_router(embarques.router)
app.include_router(dossies.router)
app.include_router(camada.router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/health/db")
def health_db():
    try:
        with engine.connect() as con:
            con.execute(text("SELECT 1"))
        return {"status": "ok", "database": "reachable"}
    except Exception:
        return {"status": "erro", "database": "unreachable"}
