from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

TipoDocumento = Literal["car", "ccir", "matricula", "licenca", "contrato", "outro"]


def _so_digitos(valor: str) -> str:
    return "".join(c for c in valor if c.isdigit())


def _cpf_valido(d: str) -> bool:
    if len(d) != 11 or d == d[0] * 11:
        return False
    for n in (9, 10):
        soma = sum(int(d[i]) * (n + 1 - i) for i in range(n))
        if (soma * 10 % 11) % 10 != int(d[n]):
            return False
    return True


def _cnpj_valido(d: str) -> bool:
    if len(d) != 14 or d == d[0] * 14:
        return False
    for n in (12, 13):
        pesos = ([5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2] if n == 12 else [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
        soma = sum(int(d[i]) * pesos[i] for i in range(n))
        resto = soma % 11
        if (0 if resto < 2 else 11 - resto) != int(d[n]):
            return False
    return True


def normalizar_documento(valor: str) -> str:
    d = _so_digitos(valor)
    if not (_cpf_valido(d) or _cnpj_valido(d)):
        raise ValueError("CPF/CNPJ inválido. Confira os dígitos.")
    return d


# ---------- auth ----------
class RegistroIn(BaseModel):
    nome: str = Field(min_length=2, max_length=255)
    email: EmailStr
    senha: str = Field(min_length=8, max_length=72)


class LoginIn(BaseModel):
    email: EmailStr
    senha: str = Field(max_length=72)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UsuarioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nome: str
    email: str


# ---------- fornecedor ----------
class FornecedorIn(BaseModel):
    nome: str = Field(min_length=2, max_length=255)
    documento: str
    email: EmailStr | None = None
    telefone: str | None = Field(default=None, max_length=30)
    municipio: str | None = Field(default=None, max_length=120)
    uf: str | None = Field(default=None, min_length=2, max_length=2)

    @field_validator("documento")
    @classmethod
    def _doc(cls, v):
        return normalizar_documento(v)


class FornecedorUpdate(BaseModel):
    nome: str | None = Field(default=None, min_length=2, max_length=255)
    documento: str | None = None
    email: EmailStr | None = None
    telefone: str | None = Field(default=None, max_length=30)
    municipio: str | None = Field(default=None, max_length=120)
    uf: str | None = Field(default=None, min_length=2, max_length=2)
    ativo: bool | None = None

    @field_validator("documento")
    @classmethod
    def _doc(cls, v):
        return None if v is None else normalizar_documento(v)


class FornecedorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nome: str
    documento: str
    tipo_pessoa: str
    email: str | None
    telefone: str | None
    municipio: str | None
    uf: str | None
    ativo: bool
    criado_em: datetime
    atualizado_em: datetime
    total_fazendas: int = 0


# ---------- fazenda ----------
class FazendaIn(BaseModel):
    fornecedor_id: int
    nome: str = Field(min_length=2, max_length=255)
    car_codigo: str | None = Field(default=None, max_length=80)
    ccir: str | None = Field(default=None, max_length=40)
    nirf: str | None = Field(default=None, max_length=20)
    matricula: str | None = Field(default=None, max_length=40)
    municipio: str | None = Field(default=None, max_length=120)
    uf: str | None = Field(default=None, min_length=2, max_length=2)
    area_declarada_ha: Decimal | None = Field(default=None, gt=0)
    geometry: dict[str, Any]


class FazendaUpdate(BaseModel):
    nome: str | None = Field(default=None, min_length=2, max_length=255)
    car_codigo: str | None = Field(default=None, max_length=80)
    ccir: str | None = Field(default=None, max_length=40)
    nirf: str | None = Field(default=None, max_length=20)
    matricula: str | None = Field(default=None, max_length=40)
    municipio: str | None = Field(default=None, max_length=120)
    uf: str | None = Field(default=None, min_length=2, max_length=2)
    area_declarada_ha: Decimal | None = Field(default=None, gt=0)
    geometry: dict[str, Any] | None = None


class FazendaOut(BaseModel):
    id: int
    fornecedor_id: int
    nome: str
    car_codigo: str | None
    ccir: str | None
    nirf: str | None
    matricula: str | None
    municipio: str | None
    uf: str | None
    area_declarada_ha: Decimal | None
    status: str
    area_sobreposta_m2: Decimal
    verificada_em: datetime | None
    camada_versao_id: int | None
    criado_em: datetime
    atualizado_em: datetime
    geometry: dict[str, Any]


class ImportarGeoJSONIn(BaseModel):
    fornecedor_id: int
    geojson: dict[str, Any]
    prop_nome: str = "cod_imovel"
    prop_car: str = "cod_imovel"
    prop_municipio: str = "municipio"
    prop_area_ha: str = "num_area"


# ---------- documento ----------
class DocumentoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    fornecedor_id: int | None
    fazenda_id: int | None
    tipo: str
    nome_arquivo: str
    content_type: str
    tamanho_bytes: int
    sha256: str
    validade: date | None
    criado_em: datetime


# ---------- embarque ----------
class EmbarqueIn(BaseModel):
    identificacao: str = Field(min_length=1, max_length=120)
    data_embarque: date
    destino: str = Field(min_length=2, max_length=255)


class ParcelaIn(BaseModel):
    fazenda_id: int
    quantidade_kg: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    observacao: str | None = None


class ParcelasIn(BaseModel):
    parcelas: list[ParcelaIn]


class ParcelaOut(BaseModel):
    id: int
    fazenda_id: int
    fazenda_nome: str
    fazenda_status: str
    quantidade_kg: Decimal
    observacao: str | None


class EmbarqueOut(BaseModel):
    id: int
    identificacao: str
    data_embarque: date
    destino: str
    status: str
    fechado_em: datetime | None
    criado_em: datetime
    parcelas: list[ParcelaOut] = []
    total_kg: Decimal = Decimal(0)
    dossie_id: int | None = None


class DossieOut(BaseModel):
    id: int
    embarque_id: int
    embarque_identificacao: str
    destino: str
    data_embarque: date
    n_parcelas: int
    total_kg: Decimal
    gerado_em: datetime
    retrato: dict[str, Any] | None = None
