"""camada comum de imóveis do CAR: imovel_versao e imovel

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-01
"""
import geoalchemy2
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "imovel_versao",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("origem", sa.String(120), nullable=False),
        sa.Column("uf", sa.String(2)),
        sa.Column("arquivo", sa.String(255)),
        sa.Column("n_feicoes", sa.Integer, nullable=False),
        sa.Column("carregada_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "imovel",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("cod_imovel", sa.String(80), nullable=False, unique=True),
        sa.Column("municipio", sa.String(120)),
        sa.Column("uf", sa.String(2)),
        sa.Column("area_ha", sa.Numeric(14, 4)),
        sa.Column("situacao", sa.String(20)),
        sa.Column("condicao", sa.String(255)),
        sa.Column(
            "versao_id", sa.BigInteger, sa.ForeignKey("imovel_versao.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "geom",
            geoalchemy2.Geometry("GEOMETRY", srid=4326, spatial_index=False, from_text="ST_GeomFromEWKT", name="geometry"),
            nullable=False,
        ),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_imovel_versao_id", "imovel", ["versao_id"])
    op.create_index("idx_imovel_geom", "imovel", ["geom"], postgresql_using="gist")
    op.create_index("idx_imovel_uf", "imovel", ["uf"])


def downgrade() -> None:
    op.drop_table("imovel")
    op.drop_table("imovel_versao")
