"""produto e especificação de qualidade do embarque

Colunas opcionais: o código anterior continua funcionando com elas (migração aplicada antes do merge).

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-18
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

_COLUNAS = (
    ("produto", 40),
    ("tipo_classificacao", 20),
    ("bebida", 40),
    ("peneira", 20),
    ("regiao_origem", 120),
)


def upgrade() -> None:
    for nome, tamanho in _COLUNAS:
        op.add_column("embarque", sa.Column(nome, sa.String(tamanho), nullable=True))


def downgrade() -> None:
    for nome, _ in reversed(_COLUNAS):
        op.drop_column("embarque", nome)
