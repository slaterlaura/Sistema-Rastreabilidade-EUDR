"""Mapa de calor: desmatamento pós-corte pré-agregado em células (prodes_calor)."""

import importlib.util
import sys
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import box
from sqlalchemy import text

from app.config import settings
from app.database import engine
from scripts.comum_carga import atualizar_calor

# A e B caem na mesma célula de 0,25° (nível 0) mas em células diferentes de 0,05° (nível 1).
# C é de 2019 (antes do corte) e nunca entra no calor.
A = (-49.99, -20.99, 1.0, 2022)   # lon, lat, area_km, ano  → 100 ha
B = (-49.93, -20.97, 3.0, 2023)   # → 300 ha
C = (-45.00, -15.00, 9.0, 2019)


@pytest.fixture
def poligonos():
    with engine.begin() as con:
        vid = con.execute(
            text("INSERT INTO camada_versao (origem, bioma, n_feicoes) VALUES ('PRODES','Teste',3) RETURNING id")
        ).scalar_one()
        for lon, lat, area_km, ano in (A, B, C):
            con.execute(
                text(
                    "INSERT INTO camada_prodes (versao_id, ano, area_km, geom) "
                    "VALUES (:v, :ano, :a, ST_MakeEnvelope(:x - 0.001, :y - 0.001, :x + 0.001, :y + 0.001, 4326))"
                ),
                {"v": vid, "ano": ano, "a": area_km, "x": lon, "y": lat},
            )
    with engine.begin() as con:
        return atualizar_calor(con, settings.ano_corte)


def _pontos(nivel):
    with engine.connect() as con:
        return con.execute(
            text("SELECT lat, lon, area_ha, n FROM prodes_calor WHERE nivel = :n ORDER BY lon"), {"n": nivel}
        ).all()


def test_agrega_por_celula_e_ignora_antes_do_corte(poligonos):
    assert poligonos == {0: 1, 1: 2}
    (p0,) = _pontos(0)
    assert p0.n == 2 and p0.area_ha == pytest.approx(400)
    assert [round(p.area_ha) for p in _pontos(1)] == [100, 300]


def test_centro_ponderado_pela_area(poligonos):
    (p0,) = _pontos(0)
    # mais perto de B (300 ha) que de A (100 ha)
    assert p0.lon == pytest.approx((A[0] * 100 + B[0] * 300) / 400, abs=1e-6)
    assert p0.lat == pytest.approx((A[1] * 100 + B[1] * 300) / 400, abs=1e-6)


def test_recalcular_substitui_o_anterior(poligonos):
    with engine.begin() as con:
        con.execute(text("DELETE FROM camada_prodes WHERE area_km = 3.0"))
        assert atualizar_calor(con, settings.ano_corte) == {0: 1, 1: 1}
    assert _pontos(0)[0].area_ha == pytest.approx(100)


def test_carga_do_prodes_recalcula_o_calor(tmp_path):
    _spec = importlib.util.spec_from_file_location(
        "carga_prodes_calor", Path(__file__).resolve().parents[1] / "scripts" / "carga_prodes.py"
    )
    carga = importlib.util.module_from_spec(_spec)
    sys.modules["carga_prodes_calor"] = carga
    _spec.loader.exec_module(carga)
    gdf = gpd.GeoDataFrame(
        {"state": ["MG", "MG"], "year": [2022, 2024], "area_km": [0.5, 0.2]},
        geometry=[box(-46, -19, -45.99, -18.99), box(-45, -19, -44.99, -18.99)],
        crs="EPSG:4674",
    )
    shp = tmp_path / "prodes.shp"
    gdf.to_file(shp)
    carga.executar(["--arquivo", str(shp), "--bioma", "Cerrado"])
    assert [round(p.area_ha) for p in _pontos(0)] == [50, 20]


def test_endpoint_devolve_pontos_compactos_e_max(client, auth, poligonos):
    r = client.get("/camada/prodes/calor?nivel=0&bbox=-75,-35,-30,7", headers=auth)  # Brasil inteiro
    assert r.status_code == 200 and "max-age" in r.headers["cache-control"]
    corpo = r.json()
    assert corpo["nivel"] == 0 and not corpo["truncado"] and len(corpo["pontos"]) == 1
    lat, lon, ha = corpo["pontos"][0]
    assert ha == pytest.approx(400) and corpo["max"] == pytest.approx(400)
    r1 = client.get("/camada/prodes/calor?nivel=1&bbox=-50.5,-21.5,-49.5,-20.5", headers=auth)
    assert sorted(p[2] for p in r1.json()["pontos"]) == [100, 300]


def test_endpoint_valida_nivel_recorte_e_login(client, auth, poligonos):
    assert client.get("/camada/prodes/calor?nivel=1&bbox=-75,-35,-30,7", headers=auth).status_code == 400  # nível fino, área grande
    assert client.get("/camada/prodes/calor?nivel=2&bbox=-50,-21,-49,-20", headers=auth).status_code == 422
    assert client.get("/camada/prodes/calor?nivel=0&bbox=a,b,c,d", headers=auth).status_code == 400
    assert client.get("/camada/prodes/calor?nivel=0&bbox=-75,-35,-30,7").status_code == 401


def test_recorte_sem_desmatamento_devolve_vazio(client, auth, poligonos):
    corpo = client.get("/camada/prodes/calor?nivel=0&bbox=-40,-10,-35,-5", headers=auth).json()
    assert corpo["pontos"] == [] and corpo["max"] == 0
