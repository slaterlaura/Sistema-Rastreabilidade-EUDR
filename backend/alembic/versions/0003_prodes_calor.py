"""mapa de calor: desmatamento pré-agregado em células (prodes_calor)

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-06
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prodes_calor",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("nivel", sa.SmallInteger, nullable=False),
        sa.Column("lat", sa.Float, nullable=False),
        sa.Column("lon", sa.Float, nullable=False),
        sa.Column("area_ha", sa.Float, nullable=False),
        sa.Column("n", sa.Integer, nullable=False),
    )
    op.create_index("idx_prodes_calor_nivel_lat_lon", "prodes_calor", ["nivel", "lat", "lon"])


def downgrade() -> None:
    op.drop_table("prodes_calor")
