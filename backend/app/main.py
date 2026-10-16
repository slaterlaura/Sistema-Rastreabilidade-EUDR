import json
import logging
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import FastAPI, HTTPException, Query, status
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.database import check_db_connection, engine, ensure_eudr_schema


logger = logging.getLogger(__name__)

app = FastAPI(
    title="Sistema de Rastreabilidade EUDR",
    version="0.2.0",
)


class FornecedorCreate(BaseModel):
    nome: str = Field(..., min_length=1)
    cpf_cnpj: str = Field(..., min_length=11, max_length=20)
    car_codigo: str | None = None


class FornecedorUpdate(BaseModel):
    nome: str | None = None
    cpf_cnpj: str | None = None
    car_codigo: str | None = None


class FazendaCreate(BaseModel):
    fornecedor_id: int
    codigo_externo: str | None = None
    nome: str | None = None
    municipio: str | None = None
    area_ha: float | None = None
    geometry: dict[str, Any]


class FazendaUpdate(BaseModel):
    fornecedor_id: int | None = None
    codigo_externo: str | None = None
    nome: str | None = None
    municipio: str | None = None
    area_ha: float | None = None
    geometry: dict[str, Any] | None = None


class FazendaImportGeoJSONRequest(BaseModel):
    fornecedor_id: int
    geojson: dict[str, Any]
    codigo_externo_property: str = "cod_imovel"
    nome_property: str = "cod_imovel"
    municipio_property: str = "municipio"
    area_ha_property: str = "num_area"


class EmbarqueCreate(BaseModel):
    identificacao: str = Field(..., min_length=1)
    data_embarque: date
    destino: str = Field(..., min_length=1)
    fazenda_ids: list[int] = Field(default_factory=list)


class EmbarqueUpdate(BaseModel):
    identificacao: str | None = None
    data_embarque: date | None = None
    destino: str | None = None
    fazenda_ids: list[int] | None = None


def _require_engine():
    if engine is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DATABASE_URL nao configurado.",
        )
    return engine


def _model_to_dict(model: BaseModel, *, exclude_none: bool = False) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(exclude_none=exclude_none)
    return model.dict(exclude_none=exclude_none)


def _to_mapping_row(row: Any) -> dict[str, Any]:
    payload = dict(row)
    if "geometry" in payload and isinstance(payload["geometry"], str):
        payload["geometry"] = json.loads(payload["geometry"])
    if "fazenda_ids" in payload and payload["fazenda_ids"] is None:
        payload["fazenda_ids"] = []
    return payload


def _extract_geometry(geometry_payload: dict[str, Any]) -> dict[str, Any]:
    geo_type = geometry_payload.get("type")
    if geo_type == "Feature":
        geometry = geometry_payload.get("geometry")
    else:
        geometry = geometry_payload

    if not isinstance(geometry, dict) or geometry.get("type") not in {
        "Polygon",
        "MultiPolygon",
    }:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Geometry invalida. Use Polygon, MultiPolygon ou Feature GeoJSON.",
        )
    return geometry


def _fornecedor_exists(conn, fornecedor_id: int) -> bool:
    row = conn.execute(
        text("SELECT 1 FROM eudr.fornecedor WHERE id = :id"),
        {"id": fornecedor_id},
    ).first()
    return row is not None


def _insert_fazenda_with_spatial_check(conn, payload: FazendaCreate) -> dict[str, Any]:
    if not _fornecedor_exists(conn, payload.fornecedor_id):
        raise HTTPException(status_code=404, detail="Fornecedor nao encontrado.")

    geometry = _extract_geometry(payload.geometry)
    geom_json = json.dumps(geometry, ensure_ascii=False)
    stmt = text(
        """
        WITH geom_input AS (
            SELECT ST_Multi(
                ST_CollectionExtract(
                    ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(:geom_json), 4326)),
                    3
                )
            )::geometry(MultiPolygon, 4326) AS geom
        ),
        analise AS (
            SELECT
                COALESCE(
                    SUM(ST_Area(ST_Intersection(g.geom, p.geom)::geography)),
                    0
                )::numeric(18, 2) AS area_sobreposta_m2
            FROM geom_input g
            LEFT JOIN eudr.camada_prodes p ON ST_Intersects(g.geom, p.geom)
        )
        INSERT INTO eudr.fazenda (
            fornecedor_id,
            codigo_externo,
            nome,
            municipio,
            area_ha,
            status_conformidade,
            area_sobreposta_m2,
            geom
        )
        SELECT
            :fornecedor_id,
            :codigo_externo,
            :nome,
            :municipio,
            :area_ha,
            CASE WHEN a.area_sobreposta_m2 > 0 THEN 'bloqueada' ELSE 'apta' END,
            a.area_sobreposta_m2,
            g.geom
        FROM geom_input g
        CROSS JOIN analise a
        RETURNING
            id,
            fornecedor_id,
            codigo_externo,
            nome,
            municipio,
            area_ha,
            status_conformidade,
            area_sobreposta_m2,
            ST_AsGeoJSON(geom)::json AS geometry,
            criado_em,
            atualizado_em
        """
    )
    row = conn.execute(
        stmt,
        {
            "fornecedor_id": payload.fornecedor_id,
            "codigo_externo": payload.codigo_externo,
            "nome": payload.nome,
            "municipio": payload.municipio,
            "area_ha": payload.area_ha,
            "geom_json": geom_json,
        },
    ).mappings().first()
    if row is None:
        raise HTTPException(400, detail="Nao foi possivel criar fazenda.")
    return _to_mapping_row(row)


def _validate_fazendas_aptas(conn, fazenda_ids: list[int]) -> None:
    if not fazenda_ids:
        return

    rows = conn.execute(
        text(
            """
            SELECT id, status_conformidade
            FROM eudr.fazenda
            WHERE id = ANY(:ids)
            """
        ),
        {"ids": fazenda_ids},
    ).mappings().all()

    found = {row["id"] for row in rows}
    missing = sorted(set(fazenda_ids) - found)
    if missing:
        raise HTTPException(
            status_code=404,
            detail=f"Fazendas nao encontradas: {missing}",
        )

    blocked = [row["id"] for row in rows if row["status_conformidade"] != "apta"]
    if blocked:
        raise HTTPException(
            status_code=400,
            detail=f"Fazendas bloqueadas nao podem entrar no embarque: {blocked}",
        )


def _get_embarque(conn, embarque_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        text(
            """
            SELECT
                e.id,
                e.identificacao,
                e.data_embarque,
                e.destino,
                e.criado_em,
                e.atualizado_em,
                COALESCE(
                    ARRAY_AGG(ef.fazenda_id ORDER BY ef.fazenda_id)
                    FILTER (WHERE ef.fazenda_id IS NOT NULL),
                    ARRAY[]::bigint[]
                ) AS fazenda_ids
            FROM eudr.embarque e
            LEFT JOIN eudr.embarque_fazenda ef ON ef.embarque_id = e.id
            WHERE e.id = :id
            GROUP BY e.id
            """
        ),
        {"id": embarque_id},
    ).mappings().first()
    if row is None:
        return None
    return _to_mapping_row(row)


@app.on_event("startup")
def startup_event() -> None:
    try:
        ensure_eudr_schema()
    except Exception as exc:  # pragma: no cover
        logger.warning("Falha ao validar schema eudr no startup: %s", exc)


@app.get("/")
def read_root():
    return {
        "service": "Sistema de Rastreabilidade EUDR",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/health/db")
def health_db():
    if check_db_connection():
        return {"status": "ok", "database": "reachable"}
    return {"status": "warning", "database": "unreachable_or_not_configured"}


# -------------------------------------------------------------------
# CRUD FORNECEDOR
# -------------------------------------------------------------------
@app.get("/fornecedores")
def list_fornecedores():
    db = _require_engine()
    with db.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id, nome, cpf_cnpj, car_codigo, criado_em, atualizado_em
                FROM eudr.fornecedor
                ORDER BY id
                """
            )
        ).mappings()
        return [_to_mapping_row(row) for row in rows]


@app.post("/fornecedores", status_code=201)
def create_fornecedor(payload: FornecedorCreate):
    db = _require_engine()
    stmt = text(
        """
        INSERT INTO eudr.fornecedor (nome, cpf_cnpj, car_codigo)
        VALUES (:nome, :cpf_cnpj, :car_codigo)
        RETURNING id, nome, cpf_cnpj, car_codigo, criado_em, atualizado_em
        """
    )
    try:
        with db.begin() as conn:
            row = conn.execute(stmt, _model_to_dict(payload)).mappings().first()
            return _to_mapping_row(row)
    except IntegrityError:
        raise HTTPException(409, detail="Fornecedor com esse CPF/CNPJ ja existe.")


@app.get("/fornecedores/{fornecedor_id}")
def get_fornecedor(fornecedor_id: int):
    db = _require_engine()
    with db.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT id, nome, cpf_cnpj, car_codigo, criado_em, atualizado_em
                FROM eudr.fornecedor
                WHERE id = :id
                """
            ),
            {"id": fornecedor_id},
        ).mappings().first()
        if row is None:
            raise HTTPException(404, detail="Fornecedor nao encontrado.")
        return _to_mapping_row(row)


@app.put("/fornecedores/{fornecedor_id}")
def update_fornecedor(fornecedor_id: int, payload: FornecedorUpdate):
    db = _require_engine()
    data = _model_to_dict(payload, exclude_none=True)
    if not data:
        raise HTTPException(400, detail="Nenhum campo para atualizar.")

    allowed = {"nome", "cpf_cnpj", "car_codigo"}
    set_parts = [f"{field} = :{field}" for field in data if field in allowed]
    if not set_parts:
        raise HTTPException(400, detail="Campos invalidos para atualizacao.")

    set_parts.append("atualizado_em = NOW()")
    stmt = text(
        f"""
        UPDATE eudr.fornecedor
        SET {", ".join(set_parts)}
        WHERE id = :id
        RETURNING id, nome, cpf_cnpj, car_codigo, criado_em, atualizado_em
        """
    )
    data["id"] = fornecedor_id
    try:
        with db.begin() as conn:
            row = conn.execute(stmt, data).mappings().first()
            if row is None:
                raise HTTPException(404, detail="Fornecedor nao encontrado.")
            return _to_mapping_row(row)
    except IntegrityError:
        raise HTTPException(409, detail="CPF/CNPJ ja utilizado por outro fornecedor.")


@app.delete("/fornecedores/{fornecedor_id}", status_code=204)
def delete_fornecedor(fornecedor_id: int):
    db = _require_engine()
    try:
        with db.begin() as conn:
            deleted = conn.execute(
                text("DELETE FROM eudr.fornecedor WHERE id = :id"),
                {"id": fornecedor_id},
            )
            if deleted.rowcount == 0:
                raise HTTPException(404, detail="Fornecedor nao encontrado.")
    except IntegrityError:
        raise HTTPException(
            409,
            detail="Fornecedor possui fazendas vinculadas e nao pode ser excluido.",
        )


# -------------------------------------------------------------------
# CRUD FAZENDA + IMPORT GEOJSON + ANALISE ESPACIAL
# -------------------------------------------------------------------
@app.get("/fazendas")
def list_fazendas():
    db = _require_engine()
    with db.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT
                    id,
                    fornecedor_id,
                    codigo_externo,
                    nome,
                    municipio,
                    area_ha,
                    status_conformidade,
                    area_sobreposta_m2,
                    ST_AsGeoJSON(geom)::json AS geometry,
                    criado_em,
                    atualizado_em
                FROM eudr.fazenda
                ORDER BY id
                """
            )
        ).mappings()
        return [_to_mapping_row(row) for row in rows]


@app.post("/fazendas", status_code=201)
def create_fazenda(payload: FazendaCreate):
    db = _require_engine()
    try:
        with db.begin() as conn:
            return _insert_fazenda_with_spatial_check(conn, payload)
    except HTTPException:
        raise
    except IntegrityError as exc:
        raise HTTPException(409, detail=f"Erro de integridade ao criar fazenda: {exc}")
    except SQLAlchemyError as exc:
        raise HTTPException(400, detail=f"Erro ao processar geometria: {exc}")


@app.get("/fazendas/{fazenda_id}")
def get_fazenda(fazenda_id: int):
    db = _require_engine()
    with db.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT
                    id,
                    fornecedor_id,
                    codigo_externo,
                    nome,
                    municipio,
                    area_ha,
                    status_conformidade,
                    area_sobreposta_m2,
                    ST_AsGeoJSON(geom)::json AS geometry,
                    criado_em,
                    atualizado_em
                FROM eudr.fazenda
                WHERE id = :id
                """
            ),
            {"id": fazenda_id},
        ).mappings().first()
        if row is None:
            raise HTTPException(404, detail="Fazenda nao encontrada.")
        return _to_mapping_row(row)


@app.put("/fazendas/{fazenda_id}")
def update_fazenda(fazenda_id: int, payload: FazendaUpdate):
    db = _require_engine()
    data = _model_to_dict(payload, exclude_none=True)
    if not data:
        raise HTTPException(400, detail="Nenhum campo para atualizar.")

    try:
        with db.begin() as conn:
            if "fornecedor_id" in data and not _fornecedor_exists(conn, data["fornecedor_id"]):
                raise HTTPException(404, detail="Fornecedor nao encontrado.")

            if "geometry" in data:
                geometry = _extract_geometry(data["geometry"])
                geom_json = json.dumps(geometry, ensure_ascii=False)
                row = conn.execute(
                    text(
                        """
                        WITH geom_input AS (
                            SELECT ST_Multi(
                                ST_CollectionExtract(
                                    ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(:geom_json), 4326)),
                                    3
                                )
                            )::geometry(MultiPolygon, 4326) AS geom
                        ),
                        analise AS (
                            SELECT
                                COALESCE(
                                    SUM(ST_Area(ST_Intersection(g.geom, p.geom)::geography)),
                                    0
                                )::numeric(18, 2) AS area_sobreposta_m2
                            FROM geom_input g
                            LEFT JOIN eudr.camada_prodes p ON ST_Intersects(g.geom, p.geom)
                        )
                        UPDATE eudr.fazenda f
                        SET
                            fornecedor_id = COALESCE(:fornecedor_id, f.fornecedor_id),
                            codigo_externo = COALESCE(:codigo_externo, f.codigo_externo),
                            nome = COALESCE(:nome, f.nome),
                            municipio = COALESCE(:municipio, f.municipio),
                            area_ha = COALESCE(:area_ha, f.area_ha),
                            status_conformidade = CASE
                                WHEN a.area_sobreposta_m2 > 0 THEN 'bloqueada'
                                ELSE 'apta'
                            END,
                            area_sobreposta_m2 = a.area_sobreposta_m2,
                            geom = g.geom,
                            atualizado_em = NOW()
                        FROM geom_input g
                        CROSS JOIN analise a
                        WHERE f.id = :id
                        RETURNING
                            f.id,
                            f.fornecedor_id,
                            f.codigo_externo,
                            f.nome,
                            f.municipio,
                            f.area_ha,
                            f.status_conformidade,
                            f.area_sobreposta_m2,
                            ST_AsGeoJSON(f.geom)::json AS geometry,
                            f.criado_em,
                            f.atualizado_em
                        """
                    ),
                    {
                        "id": fazenda_id,
                        "fornecedor_id": data.get("fornecedor_id"),
                        "codigo_externo": data.get("codigo_externo"),
                        "nome": data.get("nome"),
                        "municipio": data.get("municipio"),
                        "area_ha": data.get("area_ha"),
                        "geom_json": geom_json,
                    },
                ).mappings().first()
            else:
                row = conn.execute(
                    text(
                        """
                        UPDATE eudr.fazenda
                        SET
                            fornecedor_id = COALESCE(:fornecedor_id, fornecedor_id),
                            codigo_externo = COALESCE(:codigo_externo, codigo_externo),
                            nome = COALESCE(:nome, nome),
                            municipio = COALESCE(:municipio, municipio),
                            area_ha = COALESCE(:area_ha, area_ha),
                            atualizado_em = NOW()
                        WHERE id = :id
                        RETURNING
                            id,
                            fornecedor_id,
                            codigo_externo,
                            nome,
                            municipio,
                            area_ha,
                            status_conformidade,
                            area_sobreposta_m2,
                            ST_AsGeoJSON(geom)::json AS geometry,
                            criado_em,
                            atualizado_em
                        """
                    ),
                    {
                        "id": fazenda_id,
                        "fornecedor_id": data.get("fornecedor_id"),
                        "codigo_externo": data.get("codigo_externo"),
                        "nome": data.get("nome"),
                        "municipio": data.get("municipio"),
                        "area_ha": data.get("area_ha"),
                    },
                ).mappings().first()

            if row is None:
                raise HTTPException(404, detail="Fazenda nao encontrada.")
            return _to_mapping_row(row)
    except HTTPException:
        raise
    except IntegrityError as exc:
        raise HTTPException(409, detail=f"Erro de integridade ao atualizar fazenda: {exc}")
    except SQLAlchemyError as exc:
        raise HTTPException(400, detail=f"Erro ao processar atualizacao da fazenda: {exc}")


@app.delete("/fazendas/{fazenda_id}", status_code=204)
def delete_fazenda(fazenda_id: int):
    db = _require_engine()
    try:
        with db.begin() as conn:
            deleted = conn.execute(
                text("DELETE FROM eudr.fazenda WHERE id = :id"),
                {"id": fazenda_id},
            )
            if deleted.rowcount == 0:
                raise HTTPException(404, detail="Fazenda nao encontrada.")
    except IntegrityError:
        raise HTTPException(
            409,
            detail="Fazenda vinculada a embarque e nao pode ser removida.",
        )


@app.post("/fazendas/import-geojson", status_code=201)
def import_fazendas_geojson(payload: FazendaImportGeoJSONRequest):
    db = _require_engine()
    if payload.geojson.get("type") != "FeatureCollection":
        raise HTTPException(400, detail="GeoJSON deve ser um FeatureCollection.")

    features = payload.geojson.get("features", [])
    if not isinstance(features, list) or not features:
        raise HTTPException(400, detail="GeoJSON sem features para importar.")

    created_ids: list[int] = []
    try:
        with db.begin() as conn:
            if not _fornecedor_exists(conn, payload.fornecedor_id):
                raise HTTPException(404, detail="Fornecedor nao encontrado.")

            for idx, feature in enumerate(features):
                if not isinstance(feature, dict):
                    raise HTTPException(400, detail=f"Feature {idx} invalida.")
                props = feature.get("properties") or {}
                geometry = feature.get("geometry")
                request = FazendaCreate(
                    fornecedor_id=payload.fornecedor_id,
                    codigo_externo=props.get(payload.codigo_externo_property),
                    nome=props.get(payload.nome_property),
                    municipio=props.get(payload.municipio_property),
                    area_ha=props.get(payload.area_ha_property),
                    geometry=geometry,
                )
                created = _insert_fazenda_with_spatial_check(conn, request)
                created_ids.append(created["id"])
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise HTTPException(400, detail=f"Falha ao importar GeoJSON: {exc}")

    return {"importadas": len(created_ids), "fazenda_ids": created_ids}


# -------------------------------------------------------------------
# CRUD EMBARQUE
# -------------------------------------------------------------------
@app.get("/embarques")
def list_embarques():
    db = _require_engine()
    with db.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT
                    e.id,
                    e.identificacao,
                    e.data_embarque,
                    e.destino,
                    e.criado_em,
                    e.atualizado_em,
                    COALESCE(
                        ARRAY_AGG(ef.fazenda_id ORDER BY ef.fazenda_id)
                        FILTER (WHERE ef.fazenda_id IS NOT NULL),
                        ARRAY[]::bigint[]
                    ) AS fazenda_ids
                FROM eudr.embarque e
                LEFT JOIN eudr.embarque_fazenda ef ON ef.embarque_id = e.id
                GROUP BY e.id
                ORDER BY e.id
                """
            )
        ).mappings()
        return [_to_mapping_row(row) for row in rows]


@app.post("/embarques", status_code=201)
def create_embarque(payload: EmbarqueCreate):
    db = _require_engine()
    fazenda_ids = sorted(set(payload.fazenda_ids))
    try:
        with db.begin() as conn:
            _validate_fazendas_aptas(conn, fazenda_ids)
            embarque_row = conn.execute(
                text(
                    """
                    INSERT INTO eudr.embarque (identificacao, data_embarque, destino)
                    VALUES (:identificacao, :data_embarque, :destino)
                    RETURNING id
                    """
                ),
                {
                    "identificacao": payload.identificacao,
                    "data_embarque": payload.data_embarque,
                    "destino": payload.destino,
                },
            ).mappings().first()

            embarque_id = embarque_row["id"]
            if fazenda_ids:
                conn.execute(
                    text(
                        """
                        INSERT INTO eudr.embarque_fazenda (embarque_id, fazenda_id)
                        VALUES (:embarque_id, :fazenda_id)
                        """
                    ),
                    [
                        {"embarque_id": embarque_id, "fazenda_id": fazenda_id}
                        for fazenda_id in fazenda_ids
                    ],
                )
            result = _get_embarque(conn, embarque_id)
            return result
    except HTTPException:
        raise
    except IntegrityError as exc:
        raise HTTPException(409, detail=f"Erro de integridade ao criar embarque: {exc}")


@app.get("/embarques/{embarque_id}")
def get_embarque(embarque_id: int):
    db = _require_engine()
    with db.connect() as conn:
        row = _get_embarque(conn, embarque_id)
        if row is None:
            raise HTTPException(404, detail="Embarque nao encontrado.")
        return row


@app.put("/embarques/{embarque_id}")
def update_embarque(embarque_id: int, payload: EmbarqueUpdate):
    db = _require_engine()
    data = _model_to_dict(payload, exclude_none=True)
    if not data:
        raise HTTPException(400, detail="Nenhum campo para atualizar.")

    try:
        with db.begin() as conn:
            row_exists = conn.execute(
                text("SELECT 1 FROM eudr.embarque WHERE id = :id"),
                {"id": embarque_id},
            ).first()
            if row_exists is None:
                raise HTTPException(404, detail="Embarque nao encontrado.")

            if any(key in data for key in ("identificacao", "data_embarque", "destino")):
                conn.execute(
                    text(
                        """
                        UPDATE eudr.embarque
                        SET
                            identificacao = COALESCE(:identificacao, identificacao),
                            data_embarque = COALESCE(:data_embarque, data_embarque),
                            destino = COALESCE(:destino, destino),
                            atualizado_em = NOW()
                        WHERE id = :id
                        """
                    ),
                    {
                        "id": embarque_id,
                        "identificacao": data.get("identificacao"),
                        "data_embarque": data.get("data_embarque"),
                        "destino": data.get("destino"),
                    },
                )

            if "fazenda_ids" in data:
                fazenda_ids = sorted(set(data["fazenda_ids"]))
                _validate_fazendas_aptas(conn, fazenda_ids)
                conn.execute(
                    text("DELETE FROM eudr.embarque_fazenda WHERE embarque_id = :id"),
                    {"id": embarque_id},
                )
                if fazenda_ids:
                    conn.execute(
                        text(
                            """
                            INSERT INTO eudr.embarque_fazenda (embarque_id, fazenda_id)
                            VALUES (:embarque_id, :fazenda_id)
                            """
                        ),
                        [
                            {"embarque_id": embarque_id, "fazenda_id": fazenda_id}
                            for fazenda_id in fazenda_ids
                        ],
                    )

            result = _get_embarque(conn, embarque_id)
            return result
    except HTTPException:
        raise
    except IntegrityError as exc:
        raise HTTPException(409, detail=f"Erro de integridade ao atualizar embarque: {exc}")


@app.delete("/embarques/{embarque_id}", status_code=204)
def delete_embarque(embarque_id: int):
    db = _require_engine()
    with db.begin() as conn:
        deleted = conn.execute(
            text("DELETE FROM eudr.embarque WHERE id = :id"),
            {"id": embarque_id},
        )
        if deleted.rowcount == 0:
            raise HTTPException(404, detail="Embarque nao encontrado.")