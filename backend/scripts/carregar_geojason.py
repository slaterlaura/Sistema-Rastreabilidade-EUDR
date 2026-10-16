#!/usr/bin/env python3
"""
Carrega os GeoJSON do MVP (SICAR + PRODES) em tabelas raw no PostGIS.

Uso:
  DATABASE_URL="postgresql://user:pass@host:5432/dbname" \
  python backend/scripts/load_geojson_mvp.py \
    --fazenda data/processed/sicar_area_imovel_adamantina_mvp.geojson \
    --prodes data/processed/prodes_sp_mata_atlantica_pos2020_mvp.geojson
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

import psycopg2
from psycopg2.extras import execute_values


def _load_feature_collection(path: str) -> list[dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    if payload.get("type") != "FeatureCollection":
        raise ValueError(f"{path} nao eh FeatureCollection")

    features = payload.get("features", [])
    if not isinstance(features, list):
        raise ValueError(f"{path} possui features invalidas")

    return features


def _as_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def create_tables(conn: psycopg2.extensions.connection) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE EXTENSION IF NOT EXISTS postgis;

            CREATE TABLE IF NOT EXISTS public.fazenda_base_raw (
                cod_imovel TEXT,
                municipio TEXT,
                num_area DOUBLE PRECISION,
                des_condic TEXT,
                ind_status TEXT,
                geom geometry(MultiPolygon, 4326)
            );

            CREATE TABLE IF NOT EXISTS public.prodes_base_raw (
                fid BIGINT,
                state TEXT,
                year INTEGER,
                class_name TEXT,
                area_km DOUBLE PRECISION,
                geom geometry(MultiPolygon, 4326)
            );
            """
        )
    conn.commit()


def load_fazendas(conn: psycopg2.extensions.connection, path: str) -> int:
    features = _load_feature_collection(path)
    rows: list[tuple[Any, ...]] = []

    for feature in features:
        props = feature.get("properties") or {}
        geom = feature.get("geometry")
        if not geom:
            continue
        rows.append(
            (
                props.get("cod_imovel"),
                props.get("municipio"),
                _as_float(props.get("num_area")),
                props.get("des_condic"),
                props.get("ind_status"),
                json.dumps(geom, ensure_ascii=False),
            )
        )

    with conn.cursor() as cur:
        cur.execute("TRUNCATE TABLE public.fazenda_base_raw;")
        execute_values(
            cur,
            """
            INSERT INTO public.fazenda_base_raw
                (cod_imovel, municipio, num_area, des_condic, ind_status, geom)
            VALUES %s
            """,
            rows,
            template="""
            (
                %s, %s, %s, %s, %s,
                ST_Multi(
                    ST_CollectionExtract(
                        ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)),
                        3
                    )
                )::geometry(MultiPolygon, 4326)
            )
            """,
            page_size=1000,
        )
    conn.commit()
    return len(rows)


def load_prodes(conn: psycopg2.extensions.connection, path: str) -> int:
    features = _load_feature_collection(path)
    rows: list[tuple[Any, ...]] = []

    for feature in features:
        props = feature.get("properties") or {}
        geom = feature.get("geometry")
        if not geom:
            continue
        rows.append(
            (
                props.get("fid"),
                props.get("state"),
                props.get("year"),
                props.get("class_name"),
                _as_float(props.get("area_km")),
                json.dumps(geom, ensure_ascii=False),
            )
        )

    with conn.cursor() as cur:
        cur.execute("TRUNCATE TABLE public.prodes_base_raw;")
        execute_values(
            cur,
            """
            INSERT INTO public.prodes_base_raw
                (fid, state, year, class_name, area_km, geom)
            VALUES %s
            """,
            rows,
            template="""
            (
                %s, %s, %s, %s, %s,
                ST_Multi(
                    ST_CollectionExtract(
                        ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)),
                        3
                    )
                )::geometry(MultiPolygon, 4326)
            )
            """,
            page_size=1000,
        )
    conn.commit()
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fazenda", required=True, help="GeoJSON de fazendas (SICAR)")
    parser.add_argument("--prodes", required=True, help="GeoJSON de desmatamento (PRODES)")
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL"),
        help="String de conexao PostgreSQL (ou use env DATABASE_URL)",
    )
    args = parser.parse_args()

    if not args.database_url:
        raise SystemExit("DATABASE_URL nao informado.")

    conn = psycopg2.connect(args.database_url)
    try:
        create_tables(conn)
        fazendas = load_fazendas(conn, args.fazenda)
        prodes = load_prodes(conn, args.prodes)
        print(f"OK: {fazendas} fazendas carregadas em public.fazenda_base_raw")
        print(f"OK: {prodes} feicoes PRODES carregadas em public.prodes_base_raw")
        print("Proximo passo: execute backend/scripts/init/02-mvp-spatial-validation.sql")
    finally:
        conn.close()


if __name__ == "__main__":
    main()