"""baseline: usuario, fornecedor, fazenda, documento, camada PRODES, embarque, parcela, dossie

Revision ID: 0001
Revises:
Create Date: 2026-10-18
"""
import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def _ts(nome: str, nullable: bool = False) -> sa.Column:
    return sa.Column(
        nome, sa.DateTime(timezone=True), server_default=None if nullable else sa.func.now(), nullable=nullable
    )


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    op.create_table(
        "usuario",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("senha_hash", sa.String(255), nullable=False),
        sa.Column("nome", sa.String(255), nullable=False),
        _ts("criado_em"),
    )

    op.create_table(
        "fornecedor",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("usuario_id", sa.BigInteger, sa.ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("nome", sa.String(255), nullable=False),
        sa.Column("documento", sa.String(20), nullable=False),
        sa.Column("tipo_pessoa", sa.String(2), nullable=False),
        sa.Column("email", sa.String(255)),
        sa.Column("telefone", sa.String(30)),
        sa.Column("municipio", sa.String(120)),
        sa.Column("uf", sa.String(2)),
        sa.Column("ativo", sa.Boolean, nullable=False, server_default="true"),
        _ts("criado_em"),
        _ts("atualizado_em"),
        sa.UniqueConstraint("usuario_id", "documento", name="uq_fornecedor_usuario_documento"),
        sa.UniqueConstraint("id", "usuario_id", name="uq_fornecedor_id_usuario"),
        sa.CheckConstraint("tipo_pessoa IN ('PF', 'PJ')", name="ck_fornecedor_tipo_pessoa"),
    )
    op.create_index("ix_fornecedor_usuario_id", "fornecedor", ["usuario_id"])

    op.create_table(
        "camada_versao",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("origem", sa.String(120), nullable=False),
        sa.Column("bioma", sa.String(60), nullable=False),
        sa.Column("uf", sa.String(2)),
        sa.Column("arquivo", sa.String(255)),
        sa.Column("n_feicoes", sa.Integer, nullable=False),
        _ts("carregada_em"),
    )

    op.create_table(
        "camada_prodes",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("versao_id", sa.BigInteger, sa.ForeignKey("camada_versao.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "geom",
            geoalchemy2.Geometry("GEOMETRY", srid=4326, spatial_index=False, from_text="ST_GeomFromEWKT", name="geometry"),
        ),
        sa.Column("ano", sa.Integer, nullable=False),
        sa.Column("class_name", sa.String(40)),
        sa.Column("area_km", sa.Numeric(14, 6)),
    )
    op.create_index("ix_camada_prodes_versao_id", "camada_prodes", ["versao_id"])
    op.create_index("idx_prodes_geom", "camada_prodes", ["geom"], postgresql_using="gist")
    op.create_index("idx_prodes_ano", "camada_prodes", ["ano"])

    op.create_table(
        "fazenda",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("usuario_id", sa.BigInteger, sa.ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("fornecedor_id", sa.BigInteger, nullable=False),
        sa.Column("nome", sa.String(255), nullable=False),
        sa.Column("car_codigo", sa.String(80)),
        sa.Column("ccir", sa.String(40)),
        sa.Column("nirf", sa.String(20)),
        sa.Column("matricula", sa.String(40)),
        sa.Column("municipio", sa.String(120)),
        sa.Column("uf", sa.String(2)),
        sa.Column("area_declarada_ha", sa.Numeric(12, 2)),
        sa.Column(
            "geom",
            geoalchemy2.Geometry("GEOMETRY", srid=4326, spatial_index=False, from_text="ST_GeomFromEWKT", name="geometry"),
            nullable=False,
        ),
        sa.Column("status", sa.String(12), nullable=False, server_default="pendente"),
        sa.Column("area_sobreposta_m2", sa.Numeric(18, 2), nullable=False, server_default="0"),
        _ts("verificada_em", nullable=True),
        sa.Column("camada_versao_id", sa.BigInteger, sa.ForeignKey("camada_versao.id")),
        _ts("criado_em"),
        _ts("atualizado_em"),
        sa.ForeignKeyConstraint(
            ["fornecedor_id", "usuario_id"],
            ["fornecedor.id", "fornecedor.usuario_id"],
            name="fk_fazenda_fornecedor_usuario",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("usuario_id", "car_codigo", name="uq_fazenda_usuario_car"),
        sa.UniqueConstraint("id", "usuario_id", name="uq_fazenda_id_usuario"),
        sa.CheckConstraint("status IN ('pendente', 'apta', 'bloqueada')", name="ck_fazenda_status"),
        sa.CheckConstraint("area_declarada_ha IS NULL OR area_declarada_ha > 0", name="ck_fazenda_area"),
    )
    op.create_index("ix_fazenda_usuario_id", "fazenda", ["usuario_id"])
    op.create_index("idx_fazenda_geom", "fazenda", ["geom"], postgresql_using="gist")
    op.create_index("idx_fazenda_fornecedor", "fazenda", ["fornecedor_id"])
    op.create_index("idx_fazenda_status", "fazenda", ["status"])

    op.create_table(
        "documento",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("usuario_id", sa.BigInteger, sa.ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("fornecedor_id", sa.BigInteger),
        sa.Column("fazenda_id", sa.BigInteger),
        sa.Column("tipo", sa.String(20), nullable=False),
        sa.Column("nome_arquivo", sa.String(255), nullable=False),
        sa.Column("caminho_storage", sa.String(500), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("tamanho_bytes", sa.BigInteger, nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("validade", sa.Date),
        _ts("criado_em"),
        sa.ForeignKeyConstraint(
            ["fornecedor_id", "usuario_id"],
            ["fornecedor.id", "fornecedor.usuario_id"],
            name="fk_documento_fornecedor_usuario",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["fazenda_id", "usuario_id"],
            ["fazenda.id", "fazenda.usuario_id"],
            name="fk_documento_fazenda_usuario",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "(fornecedor_id IS NOT NULL)::int + (fazenda_id IS NOT NULL)::int = 1",
            name="ck_documento_um_dono",
        ),
        sa.CheckConstraint(
            "tipo IN ('car', 'ccir', 'matricula', 'licenca', 'contrato', 'outro')",
            name="ck_documento_tipo",
        ),
    )
    op.create_index("idx_documento_fornecedor", "documento", ["fornecedor_id"])
    op.create_index("idx_documento_fazenda", "documento", ["fazenda_id"])

    op.create_table(
        "embarque",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("usuario_id", sa.BigInteger, sa.ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("identificacao", sa.String(120), nullable=False),
        sa.Column("data_embarque", sa.Date, nullable=False),
        sa.Column("destino", sa.String(255), nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="rascunho"),
        _ts("fechado_em", nullable=True),
        _ts("criado_em"),
        sa.UniqueConstraint("usuario_id", "identificacao", name="uq_embarque_usuario_identificacao"),
        sa.CheckConstraint("status IN ('rascunho', 'fechado')", name="ck_embarque_status"),
    )
    op.create_index("ix_embarque_usuario_id", "embarque", ["usuario_id"])

    op.create_table(
        "parcela",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("embarque_id", sa.BigInteger, sa.ForeignKey("embarque.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fazenda_id", sa.BigInteger, sa.ForeignKey("fazenda.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("quantidade_kg", sa.Numeric(14, 2), nullable=False),
        sa.Column("observacao", sa.Text),
        sa.CheckConstraint("quantidade_kg > 0", name="ck_parcela_quantidade"),
    )
    op.create_index("idx_parcela_embarque", "parcela", ["embarque_id"])
    op.create_index("idx_parcela_fazenda", "parcela", ["fazenda_id"])

    op.create_table(
        "dossie",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column(
            "embarque_id", sa.BigInteger, sa.ForeignKey("embarque.id", ondelete="RESTRICT"), nullable=False, unique=True
        ),
        _ts("gerado_em"),
        sa.Column("retrato", postgresql.JSONB, nullable=False),
        sa.Column("caminho_geojson", sa.String(500)),
        sa.Column("caminho_pdf", sa.String(500)),
    )


def downgrade() -> None:
    for tabela in ("dossie", "parcela", "embarque", "documento", "fazenda", "camada_prodes", "camada_versao", "fornecedor", "usuario"):
        op.drop_table(tabela)
