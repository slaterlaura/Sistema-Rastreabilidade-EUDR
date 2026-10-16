-- MVP pipeline: validacao espacial e classificacao EUDR
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE SCHEMA IF NOT EXISTS mvp;

DROP TABLE IF EXISTS mvp.fazenda_base CASCADE;
CREATE TABLE mvp.fazenda_base AS
SELECT
    cod_imovel,
    municipio,
    num_area,
    des_condic,
    ind_status,
    ST_CollectionExtract(
        ST_MakeValid(ST_SetSRID(geom, 4326)),
        3
    )::geometry(MultiPolygon, 4326) AS geom
FROM public.fazenda_base_raw
WHERE geom IS NOT NULL
  AND COALESCE(num_area, 0) > 0
  AND ind_status = 'AT';

DELETE FROM mvp.fazenda_base WHERE ST_IsEmpty(geom);

ALTER TABLE mvp.fazenda_base ADD COLUMN id BIGSERIAL PRIMARY KEY;
CREATE INDEX idx_fazenda_base_geom ON mvp.fazenda_base USING GIST (geom);
CREATE INDEX idx_fazenda_base_cod_imovel ON mvp.fazenda_base (cod_imovel);

DROP TABLE IF EXISTS mvp.prodes_pos2020_sp CASCADE;
CREATE TABLE mvp.prodes_pos2020_sp AS
SELECT
    fid,
    state,
    year,
    class_name,
    area_km,
    ST_CollectionExtract(
        ST_MakeValid(ST_SetSRID(geom, 4326)),
        3
    )::geometry(MultiPolygon, 4326) AS geom
FROM public.prodes_base_raw
WHERE geom IS NOT NULL
  AND state = 'SP'
  AND year > 2020;

DELETE FROM mvp.prodes_pos2020_sp WHERE ST_IsEmpty(geom);

ALTER TABLE mvp.prodes_pos2020_sp ADD COLUMN id BIGSERIAL PRIMARY KEY;
CREATE INDEX idx_prodes_sp_geom ON mvp.prodes_pos2020_sp USING GIST (geom);
CREATE INDEX idx_prodes_sp_year ON mvp.prodes_pos2020_sp (year);

ANALYZE mvp.fazenda_base;
ANALYZE mvp.prodes_pos2020_sp;

DROP TABLE IF EXISTS mvp.fazenda_resultado CASCADE;
CREATE TABLE mvp.fazenda_resultado AS
SELECT
    f.id AS fazenda_id,
    f.cod_imovel,
    f.municipio,
    f.num_area,
    CASE
        WHEN COUNT(p.id) > 0 THEN 'bloqueada'
        ELSE 'apta'
    END AS situacao,
    COALESCE(
        SUM(
            ST_Area(ST_Intersection(f.geom, p.geom)::geography)
        ),
        0
    )::numeric(18, 2) AS area_sobreposta_m2
FROM mvp.fazenda_base f
LEFT JOIN mvp.prodes_pos2020_sp p
    ON ST_Intersects(f.geom, p.geom)
GROUP BY f.id, f.cod_imovel, f.municipio, f.num_area;

ALTER TABLE mvp.fazenda_resultado
    ADD PRIMARY KEY (fazenda_id);

CREATE INDEX idx_fazenda_resultado_situacao
    ON mvp.fazenda_resultado (situacao);