from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


RAIZ = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    database_url: str

    jwt_secret: str = "troque-esta-chave-em-producao"
    jwt_algoritmo: str = "HS256"
    jwt_expira_minutos: int = 60 * 8

    # R5: sobreposição abaixo disso não bloqueia (imprecisão de borda)
    tolerancia_m2: float = 1000
    # Data de corte do EUDR: só conta supressão detectada depois de 2020
    ano_corte: int = 2020

    # Arquivos (documentos e dossiês). "local" = disco (dev/testes); "blob" = Azure Blob Storage.
    # No Functions o disco é efêmero e a Function escala para várias instâncias: produção usa "blob".
    storage_backend: Literal["local", "blob"] = "local"
    storage_dir: Path = RAIZ / "backend" / "storage"
    blob_account_url: str | None = None  # https://<conta>.blob.core.windows.net (identidade gerenciada)
    blob_connection_string: str | None = None  # só para Azurite/dev; em produção use a identidade
    blob_container: str = "origemcheck-arquivos"
    upload_max_mb: int = 10

    # Cada instância da Function abre o próprio pool: (instâncias x (pool + overflow)) tem de ficar
    # abaixo do max_connections do PostgreSQL (B1ms: ~50).
    db_pool_size: int = 3
    db_max_overflow: int = 2

    cors_origens: str = "http://localhost:5173"

    model_config = SettingsConfigDict(
        env_file=RAIZ / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
