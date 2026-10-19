from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import conferir_senha, criar_token, gerar_hash, usuario_atual
from app.database import get_db
from app.models import Usuario
from app.schemas import LoginIn, RegistroIn, TokenOut, UsuarioOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/registrar", response_model=UsuarioOut, status_code=201)
def registrar(dados: RegistroIn, db: Session = Depends(get_db)):
    email = dados.email.lower()
    if db.scalar(select(Usuario.id).where(Usuario.email == email)):
        raise HTTPException(409, detail="Já existe uma conta com este e-mail. Use /auth/login.")
    usuario = Usuario(nome=dados.nome, email=email, senha_hash=gerar_hash(dados.senha))
    db.add(usuario)
    db.commit()
    return usuario


@router.post("/login", response_model=TokenOut)
def login(dados: LoginIn, db: Session = Depends(get_db)):
    usuario = db.scalar(select(Usuario).where(Usuario.email == dados.email.lower()))
    if usuario is None or not conferir_senha(dados.senha, usuario.senha_hash):
        raise HTTPException(401, detail="E-mail ou senha incorretos.")
    return TokenOut(access_token=criar_token(usuario.id))


@router.get("/eu", response_model=UsuarioOut)
def eu(usuario: Usuario = Depends(usuario_atual)):
    return usuario
