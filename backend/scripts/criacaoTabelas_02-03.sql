-- =========================================================
-- FASE 2 COMPLETA - BANCO GEOESPACIAL EUDR (MVP)
-- =========================================================

CREATE EXTENSION IF NOT EXISTS postgis;

CREATE SCHEMA IF NOT EXISTS eudr;

-- ---------------------------------------------------------
-- 1) TABELAS PRINCIPAIS DE DOMINIO
-- ---------------------------------------------------------

-- fornecedor
CREATE TABLE IF NOT EXISTS eudr.fornecedor (
    id BIGSERIAL PRIMARY KEY,
    nome TEXT NOT NULL,
    cpf_cnpj VARCHAR(20) NOT NULL UNIQUE,
    car_codigo TEXT,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- camada_prodes (geom, ano)
CREATE TABLE IF NOT EXISTS eudr.camada_prodes (
    id BIGSERIAL PRIMARY KEY,
    fonte TEXT DEFAULT 'PRODES',
    estado CHAR(2),
    ano INTEGER NOT NULL,
    class_name TEXT,
    area_km DOUBLE PRECISION,
    geom geometry(MultiPolygon, 4326) NOT NULL,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- fazenda (geom, status, area_sobreposta_m2)
CREATE TABLE IF NOT EXISTS eudr.fazenda (
    id BIGSERIAL PRIMARY KEY,
    fornecedor_id BIGINT NOT NULL REFERENCES eudr.fornecedor(id) ON DELETE RESTRICT,
    codigo_externo TEXT UNIQUE, -- ex.: cod_imovel do CAR
    nome TEXT,
    municipio TEXT,
    area_ha DOUBLE PRECISION,
    status_conformidade TEXT NOT NULL DEFAULT 'pendente'
        CHECK (status_conformidade IN ('pendente', 'apta', 'bloqueada')),
    area_sobreposta_m2 NUMERIC(18,2) NOT NULL DEFAULT 0,
    geom geometry(MultiPolygon, 4326) NOT NULL,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- embarque
CREATE TABLE IF NOT EXISTS eudr.embarque (
    id BIGSERIAL PRIMARY KEY,
    identificacao TEXT NOT NULL UNIQUE,
    data_embarque DATE NOT NULL,
    destino TEXT NOT NULL,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- embarque_fazenda (N:N)
CREATE TABLE IF NOT EXISTS eudr.embarque_fazenda (
    embarque_id BIGINT NOT NULL REFERENCES eudr.embarque(id) ON DELETE CASCADE,
    fazenda_id BIGINT NOT NULL REFERENCES eudr.fazenda(id) ON DELETE RESTRICT,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (embarque_id, fazenda_id)
);

-- ---------------------------------------------------------
-- 2) INDICES (incluindo GIST)
-- ---------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_fornecedor_nome ON eudr.fornecedor (nome);
CREATE INDEX IF NOT EXISTS idx_fazenda_fornecedor ON eudr.fazenda (fornecedor_id);
CREATE INDEX IF NOT EXISTS idx_fazenda_status ON eudr.fazenda (status_conformidade);
CREATE INDEX IF NOT EXISTS idx_embarque_data ON eudr.embarque (data_embarque);
CREATE INDEX IF NOT EXISTS idx_embarque_destino ON eudr.embarque (destino);

-- espaciais
CREATE INDEX IF NOT EXISTS idx_camada_prodes_geom_gist ON eudr.camada_prodes USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_fazenda_geom_gist ON eudr.fazenda USING GIST (geom);

-- ---------------------------------------------------------
-- 3) CARGA DA CAMADA PRODES A PARTIR DA RAW
--    (apenas SP e ano > 2020 para MVP)
-- ---------------------------------------------------------

TRUNCATE TABLE eudr.camada_prodes RESTART IDENTITY;

INSERT INTO eudr.camada_prodes (fonte, estado, ano, class_name, area_km, geom)
SELECT
    'PRODES' AS fonte,
    p.state AS estado,
    p.year AS ano,
    p.class_name,
    p.area_km,
    ST_Multi(
        ST_CollectionExtract(
            ST_MakeValid(ST_SetSRID(p.geom, 4326)),
            3
        )
    )::geometry(MultiPolygon, 4326) AS geom
FROM public.prodes_base_raw p
WHERE p.geom IS NOT NULL
  AND p.state = 'SP'
  AND p.year > 2020
  AND NOT ST_IsEmpty(p.geom);

-- ---------------------------------------------------------
-- 4) CARGA INICIAL DE FORNECEDOR + FAZENDAS (MVP)
--    usando fazenda_base_raw que voce ja carregou
-- ---------------------------------------------------------

-- Fornecedor "demo" para vincular as fazendas do MVP
INSERT INTO eudr.fornecedor (nome, cpf_cnpj, car_codigo)
VALUES ('Fornecedor Demo Adamantina', '00000000000', 'CAR-DEMO-ADAMANTINA')
ON CONFLICT (cpf_cnpj) DO NOTHING;

-- pega id do fornecedor demo
WITH f AS (
    SELECT id FROM eudr.fornecedor WHERE cpf_cnpj = '00000000000' LIMIT 1
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
    f.id AS fornecedor_id,
    r.cod_imovel AS codigo_externo,
    r.cod_imovel AS nome,
    r.municipio,
    r.num_area AS area_ha,
    'pendente' AS status_conformidade,
    0 AS area_sobreposta_m2,
    ST_Multi(
        ST_CollectionExtract(
            ST_MakeValid(ST_SetSRID(r.geom, 4326)),
            3
        )
    )::geometry(MultiPolygon, 4326) AS geom
FROM public.fazenda_base_raw r
CROSS JOIN f
WHERE r.geom IS NOT NULL
  AND COALESCE(r.num_area, 0) > 0
  AND r.ind_status = 'AT'
  AND NOT ST_IsEmpty(r.geom)
ON CONFLICT (codigo_externo) DO NOTHING;

-- ---------------------------------------------------------
-- 5) CLASSIFICACAO DE CONFORMIDADE (APTA/BLOQUEADA)
-- ---------------------------------------------------------

WITH inter AS (
    SELECT
        fa.id AS fazenda_id,
        COALESCE(
            SUM(ST_Area(ST_Intersection(fa.geom, pr.geom)::geography)),
            0
        ) AS area_sobreposta_m2
    FROM eudr.fazenda fa
    LEFT JOIN eudr.camada_prodes pr
      ON ST_Intersects(fa.geom, pr.geom)
    GROUP BY fa.id
)
UPDATE eudr.fazenda fz
SET
    area_sobreposta_m2 = ROUND(inter.area_sobreposta_m2::numeric, 2),
    status_conformidade = CASE
        WHEN inter.area_sobreposta_m2 > 0 THEN 'bloqueada'
        ELSE 'apta'
    END,
    atualizado_em = NOW()
FROM inter
WHERE fz.id = inter.fazenda_id;

-- ---------------------------------------------------------
-- 6) VIEW DE RESULTADO (FACILITA API/RELATORIO)
-- ---------------------------------------------------------

CREATE OR REPLACE VIEW eudr.v_fazenda_resultado AS
SELECT
    fa.id AS fazenda_id,
    fo.nome AS fornecedor_nome,
    fa.codigo_externo,
    fa.municipio,
    fa.area_ha,
    fa.status_conformidade,
    fa.area_sobreposta_m2
FROM eudr.fazenda fa
JOIN eudr.fornecedor fo ON fo.id = fa.fornecedor_id;

-- ---------------------------------------------------------
-- 7) CONFERENCIAS
-- ---------------------------------------------------------

-- Quantidade por status
SELECT status_conformidade, COUNT(*) AS total
FROM eudr.fazenda
GROUP BY status_conformidade
ORDER BY status_conformidade;

-- Top 20 maior sobreposicao
SELECT *
FROM eudr.v_fazenda_resultado
ORDER BY area_sobreposta_m2 DESC
LIMIT 20;