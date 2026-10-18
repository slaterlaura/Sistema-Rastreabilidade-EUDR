from pathlib import Path

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

    storage_dir: Path = RAIZ / "backend" / "storage"
    upload_max_mb: int = 10

    cors_origens: str = "http://localhost:5173"

    model_config = SettingsConfigDict(
        env_file=RAIZ / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
