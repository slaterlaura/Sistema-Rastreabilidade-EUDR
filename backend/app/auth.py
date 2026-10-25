from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Usuario

_bearer = HTTPBearer(auto_error=False)


def gerar_hash(senha: str) -> str:
    return bcrypt.hashpw(senha.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def conferir_senha(senha: str, senha_hash: str) -> bool:
    try:
        return bcrypt.checkpw(senha.encode("utf-8"), senha_hash.encode("utf-8"))
    except ValueError:
        return False


def criar_token(usuario_id: int) -> str:
    expira = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expira_minutos)
    return jwt.encode({"sub": str(usuario_id), "exp": expira}, settings.jwt_secret, algorithm=settings.jwt_algoritmo)


def usuario_atual(
    credenciais: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> Usuario:
    nao_autenticado = HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        detail="Não autenticado. Faça login em /auth/login e envie o token no cabeçalho Authorization: Bearer.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credenciais is None:
        raise nao_autenticado
    try:
        dados = jwt.decode(credenciais.credentials, settings.jwt_secret, algorithms=[settings.jwt_algoritmo])
        usuario_id = int(dados["sub"])
    except (JWTError, KeyError, ValueError):
        raise nao_autenticado
    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise nao_autenticado
    return usuario
