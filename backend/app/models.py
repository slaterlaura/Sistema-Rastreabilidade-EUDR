from datetime import date, datetime
from decimal import Decimal

from geoalchemy2 import Geometry
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


STATUS_FAZENDA = ("pendente", "apta", "bloqueada")
STATUS_EMBARQUE = ("rascunho", "fechado")
TIPOS_DOCUMENTO = ("car", "ccir", "matricula", "licenca", "contrato", "outro")


class Usuario(Base):
    __tablename__ = "usuario"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    senha_hash: Mapped[str] = mapped_column(String(255))
    nome: Mapped[str] = mapped_column(String(255))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Fornecedor(Base):
    __tablename__ = "fornecedor"
    __table_args__ = (
        UniqueConstraint("usuario_id", "documento", name="uq_fornecedor_usuario_documento"),
        # permite a FK composta de fazenda (garante o mesmo dono)
        UniqueConstraint("id", "usuario_id", name="uq_fornecedor_id_usuario"),
        CheckConstraint("tipo_pessoa IN ('PF', 'PJ')", name="ck_fornecedor_tipo_pessoa"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id", ondelete="RESTRICT"), index=True)
    nome: Mapped[str] = mapped_column(String(255))
    documento: Mapped[str] = mapped_column(String(20))  # CPF/CNPJ, só dígitos
    tipo_pessoa: Mapped[str] = mapped_column(String(2))
    email: Mapped[str | None] = mapped_column(String(255))
    telefone: Mapped[str | None] = mapped_column(String(30))
    municipio: Mapped[str | None] = mapped_column(String(120))
    uf: Mapped[str | None] = mapped_column(String(2))
    ativo: Mapped[bool] = mapped_column(server_default="true")
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    fazendas: Mapped[list["Fazenda"]] = relationship(back_populates="fornecedor")


class CamadaVersao(Base):
    """Cada carga do PRODES gera uma versão; a fazenda guarda qual versão a verificou (R3)."""

    __tablename__ = "camada_versao"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    origem: Mapped[str] = mapped_column(String(120))
    bioma: Mapped[str] = mapped_column(String(60))
    uf: Mapped[str | None] = mapped_column(String(2))
    arquivo: Mapped[str | None] = mapped_column(String(255))
    n_feicoes: Mapped[int] = mapped_column(Integer)
    carregada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CamadaProdes(Base):
    __tablename__ = "camada_prodes"
    __table_args__ = (
        Index("idx_prodes_geom", "geom", postgresql_using="gist"),
        Index("idx_prodes_ano", "ano"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    versao_id: Mapped[int] = mapped_column(ForeignKey("camada_versao.id", ondelete="CASCADE"), index=True)
    geom = mapped_column(Geometry("GEOMETRY", srid=4326, spatial_index=False))
    ano: Mapped[int] = mapped_column(Integer)
    class_name: Mapped[str | None] = mapped_column(String(40))
    area_km: Mapped[float | None] = mapped_column(Numeric(14, 6))


class Fazenda(Base):
    __tablename__ = "fazenda"
    __table_args__ = (
        ForeignKeyConstraint(
            ["fornecedor_id", "usuario_id"],
            ["fornecedor.id", "fornecedor.usuario_id"],
            name="fk_fazenda_fornecedor_usuario",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("usuario_id", "car_codigo", name="uq_fazenda_usuario_car"),
        UniqueConstraint("id", "usuario_id", name="uq_fazenda_id_usuario"),
        CheckConstraint("status IN ('pendente', 'apta', 'bloqueada')", name="ck_fazenda_status"),
        CheckConstraint("area_declarada_ha IS NULL OR area_declarada_ha > 0", name="ck_fazenda_area"),
        Index("idx_fazenda_geom", "geom", postgresql_using="gist"),
        Index("idx_fazenda_fornecedor", "fornecedor_id"),
        Index("idx_fazenda_status", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id", ondelete="RESTRICT"), index=True)
    fornecedor_id: Mapped[int] = mapped_column(BigInteger)
    nome: Mapped[str] = mapped_column(String(255))
    car_codigo: Mapped[str | None] = mapped_column(String(80))
    ccir: Mapped[str | None] = mapped_column(String(40))
    nirf: Mapped[str | None] = mapped_column(String(20))
    matricula: Mapped[str | None] = mapped_column(String(40))
    municipio: Mapped[str | None] = mapped_column(String(120))
    uf: Mapped[str | None] = mapped_column(String(2))
    area_declarada_ha: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    geom = mapped_column(Geometry("GEOMETRY", srid=4326, spatial_index=False), nullable=False)
    status: Mapped[str] = mapped_column(String(12), server_default="pendente")
    area_sobreposta_m2: Mapped[Decimal] = mapped_column(Numeric(18, 2), server_default="0")
    verificada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    camada_versao_id: Mapped[int | None] = mapped_column(ForeignKey("camada_versao.id"))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    fornecedor: Mapped[Fornecedor] = relationship(
        back_populates="fazendas", foreign_keys=[fornecedor_id, usuario_id]
    )


class Documento(Base):
    __tablename__ = "documento"
    __table_args__ = (
        ForeignKeyConstraint(
            ["fornecedor_id", "usuario_id"],
            ["fornecedor.id", "fornecedor.usuario_id"],
            name="fk_documento_fornecedor_usuario",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["fazenda_id", "usuario_id"],
            ["fazenda.id", "fazenda.usuario_id"],
            name="fk_documento_fazenda_usuario",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "(fornecedor_id IS NOT NULL)::int + (fazenda_id IS NOT NULL)::int = 1",
            name="ck_documento_um_dono",
        ),
        CheckConstraint(
            "tipo IN ('car', 'ccir', 'matricula', 'licenca', 'contrato', 'outro')",
            name="ck_documento_tipo",
        ),
        Index("idx_documento_fornecedor", "fornecedor_id"),
        Index("idx_documento_fazenda", "fazenda_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id", ondelete="RESTRICT"))
    fornecedor_id: Mapped[int | None] = mapped_column(BigInteger)
    fazenda_id: Mapped[int | None] = mapped_column(BigInteger)
    tipo: Mapped[str] = mapped_column(String(20))
    nome_arquivo: Mapped[str] = mapped_column(String(255))
    caminho_storage: Mapped[str] = mapped_column(String(500))
    content_type: Mapped[str] = mapped_column(String(100))
    tamanho_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    validade: Mapped[date | None] = mapped_column(Date)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Embarque(Base):
    __tablename__ = "embarque"
    __table_args__ = (
        UniqueConstraint("usuario_id", "identificacao", name="uq_embarque_usuario_identificacao"),
        CheckConstraint("status IN ('rascunho', 'fechado')", name="ck_embarque_status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id", ondelete="RESTRICT"), index=True)
    identificacao: Mapped[str] = mapped_column(String(120))
    data_embarque: Mapped[date] = mapped_column(Date)
    destino: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(10), server_default="rascunho")
    fechado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    parcelas: Mapped[list["Parcela"]] = relationship(
        back_populates="embarque", cascade="all, delete-orphan"
    )


class Parcela(Base):
    """Parte do embarque: uma quantidade que vem de uma única fazenda."""

    __tablename__ = "parcela"
    __table_args__ = (
        CheckConstraint("quantidade_kg > 0", name="ck_parcela_quantidade"),
        Index("idx_parcela_embarque", "embarque_id"),
        Index("idx_parcela_fazenda", "fazenda_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    embarque_id: Mapped[int] = mapped_column(ForeignKey("embarque.id", ondelete="CASCADE"))
    fazenda_id: Mapped[int] = mapped_column(ForeignKey("fazenda.id", ondelete="RESTRICT"))
    quantidade_kg: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    observacao: Mapped[str | None] = mapped_column(Text)

    embarque: Mapped[Embarque] = relationship(back_populates="parcelas")
    fazenda: Mapped[Fazenda] = relationship()


class Dossie(Base):
    __tablename__ = "dossie"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    embarque_id: Mapped[int] = mapped_column(
        ForeignKey("embarque.id", ondelete="RESTRICT"), unique=True
    )
    gerado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    retrato = mapped_column(JSONB, nullable=False)
    caminho_geojson: Mapped[str | None] = mapped_column(String(500))
    caminho_pdf: Mapped[str | None] = mapped_column(String(500))
