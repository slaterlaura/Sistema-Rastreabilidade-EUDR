"""Carga do PRODES direto de shapefile/zip, com recorte por UF e ano (scripts/carga_prodes.py)."""

import importlib.util
import json
import sys
import zipfile
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import box
from sqlalchemy import text

from app.database import engine

_spec = importlib.util.spec_from_file_location(
    "carga_prodes", Path(__file__).resolve().parents[1] / "scripts" / "carga_prodes.py"
)
carga = importlib.util.module_from_spec(_spec)
sys.modules["carga_prodes"] = carga  # o @dataclass procura o módulo aqui
_spec.loader.exec_module(carga)


def _shapefile(pasta: Path, nome="prodes", *, anos=(2019, 2021, 2023), ufs=("MG", "MG", "SP"), crs="EPSG:4674") -> Path:
    """Três polígonos pequenos, um por (ano, UF), no formato do TerraBrasilis."""
    gdf = gpd.GeoDataFrame(
        {
            "state": list(ufs),
            "year": list(anos),
            "class_name": [f"d{a}" for a in anos],
            "area_km": [0.5] * len(anos),
        },
        geometry=[box(-46 + i, -19, -45.99 + i, -18.99) for i in range(len(anos))],
        crs=crs,
    )
    caminho = pasta / f"{nome}.shp"
    gdf.to_file(caminho)
    return caminho


def _zipar(shp: Path) -> Path:
    destino = shp.with_suffix(".zip")
    with zipfile.ZipFile(destino, "w") as z:
        for parte in shp.parent.glob(f"{shp.stem}.*"):
            if parte.suffix != ".zip":
                z.write(parte, parte.name)
    return destino


def _camada():
    with engine.connect() as con:
        return con.execute(
            text(
                "SELECT v.bioma, v.uf, p.ano, ST_SRID(p.geom) AS srid FROM camada_prodes p "
                "JOIN camada_versao v ON v.id = p.versao_id ORDER BY v.bioma, p.ano"
            )
        ).all()


def test_shapefile_em_sirgas_carrega_so_a_uf_e_os_anos_pos_corte(tmp_path):
    shp = _shapefile(tmp_path)
    versao = carga.executar(["--arquivo", str(shp), "--bioma", "Cerrado", "--uf", "mg"])
    assert versao is not None
    linhas = _camada()
    # 2019 (antes do corte) e SP (outra UF) ficaram de fora
    assert [(l.bioma, l.uf, l.ano, l.srid) for l in linhas] == [("Cerrado", "MG", 2021, 4326)]


def test_le_o_zip_baixado_sem_descompactar(tmp_path):
    zipado = _zipar(_shapefile(tmp_path))
    carga.executar(["--arquivo", str(zipado), "--bioma", "Cerrado", "--uf", "SP"])
    assert [(l.uf, l.ano) for l in _camada()] == [("SP", 2023)]


def test_ano_como_rotulo_de_periodo_vira_o_ano_final(tmp_path):
    shp = _shapefile(tmp_path, anos=("2019_2020", "2020_2021", "2022_2023"), ufs=("MG", "MG", "MG"))
    gdf, resumo = carga.ler_camada(shp, uf="MG")
    assert not resumo.filtro_ano_na_leitura  # texto: filtrado em memória
    assert sorted(gdf["ano"]) == [2021, 2023]


def test_todos_os_anos_mantem_os_anteriores_ao_corte(tmp_path):
    gdf, _ = carga.ler_camada(_shapefile(tmp_path), uf="MG", todos_os_anos=True)
    assert sorted(gdf["ano"]) == [2019, 2021]


def test_shapefile_sem_prj_e_recusado_sem_crs_de_origem(tmp_path):
    shp = _shapefile(tmp_path)
    shp.with_suffix(".prj").unlink()
    with pytest.raises(SystemExit, match="--crs-origem"):
        carga.ler_camada(shp, uf="MG")
    gdf, resumo = carga.ler_camada(shp, uf="MG", crs_origem="EPSG:4674")
    assert len(gdf) == 1 and resumo.crs_origem == "EPSG:4674" and gdf.crs.to_epsg() == 4326


def test_somente_converter_grava_geojson_e_nao_toca_no_banco(tmp_path):
    saida = tmp_path / "saida" / "prodes_mg.geojson"
    assert carga.executar(["--arquivo", str(_shapefile(tmp_path)), "--uf", "MG", "--somente-converter", str(saida)]) is None
    colecao = json.loads(saida.read_text())
    assert [f["properties"]["ano"] for f in colecao["features"]] == [2021]
    assert colecao["features"][0]["geometry"]["type"] == "Polygon"
    assert _camada() == []
    # o GeoJSON gerado pode ser carregado depois
    carga.executar(["--arquivo", str(saida), "--bioma", "Cerrado", "--uf", "MG"])
    assert [(l.uf, l.ano) for l in _camada()] == [("MG", 2021)]


def test_recarga_substitui_o_mesmo_bioma_e_uf_e_mantem_os_outros(tmp_path):
    shp = _shapefile(tmp_path)
    carga.executar(["--arquivo", str(shp), "--bioma", "Cerrado", "--uf", "MG"])
    carga.executar(["--arquivo", str(shp), "--bioma", "Mata Atlantica", "--uf", "SP"])
    carga.executar(["--arquivo", str(shp), "--bioma", "Cerrado", "--uf", "MG"])
    assert [(l.bioma, l.uf, l.ano) for l in _camada()] == [("Cerrado", "MG", 2021), ("Mata Atlantica", "SP", 2023)]


def test_uf_sem_resultado_aborta(tmp_path):
    with pytest.raises(SystemExit, match="Nenhuma feição"):
        carga.executar(["--arquivo", str(_shapefile(tmp_path)), "--bioma", "Cerrado", "--uf", "BA"])


def test_arquivo_sem_coluna_de_uf_avisa_e_carrega_tudo(tmp_path):
    gdf = gpd.GeoDataFrame({"year": [2022, 2023]}, geometry=[box(-46, -19, -45.99, -18.99), box(-45, -19, -44.99, -18.99)], crs="EPSG:4674")
    shp = tmp_path / "sem_uf.shp"
    gdf.to_file(shp)
    lido, resumo = carga.ler_camada(shp, uf="MG")
    assert len(lido) == 2 and resumo.avisos and "coluna de UF" in resumo.avisos[0]


def test_carga_exige_bioma(tmp_path):
    with pytest.raises(SystemExit, match="--bioma"):
        carga.executar(["--arquivo", str(_shapefile(tmp_path)), "--uf", "MG"])


# --- casos encontrados nos arquivos reais do TerraBrasilis -------------------------------------


def _shapefile_livre(pasta: Path, nome: str, **colunas) -> Path:
    n = len(next(iter(colunas.values())))
    gdf = gpd.GeoDataFrame(colunas, geometry=[box(-46 + i, -19, -45.99 + i, -18.99) for i in range(n)], crs="EPSG:4674")
    caminho = pasta / f"{nome}.shp"
    gdf.to_file(caminho)
    return caminho


def test_uf_por_sigla_ou_por_nome_por_extenso(tmp_path):
    # Cerrado: "MINAS GERAIS"; Mata Atlântica: "MG"; Pampa: as duas misturadas
    shp = _shapefile_livre(
        tmp_path, "ufs",
        state=["MINAS GERAIS", "MG", "Minas Gerais", "SÃO PAULO", "SAO PAULO"],
        year=[2022] * 5,
    )
    mg, resumo = carga.ler_camada(shp, uf="mg")
    assert len(mg) == 3 and resumo.filtro_uf == "MG"
    sp, _ = carga.ler_camada(shp, uf="SP")
    assert len(sp) == 2


def test_uf_inexistente_e_recusada(tmp_path):
    shp = _shapefile_livre(tmp_path, "x", state=["MG"], year=[2022])
    with pytest.raises(SystemExit, match="sigla"):
        carga.ler_camada(shp, uf="XX")


def test_so_desmatamento_por_padrao(tmp_path):
    shp = _shapefile_livre(
        tmp_path, "classes",
        state=["MG"] * 3, year=[2022] * 3, main_class=["DESMATAMENTO", "RESERVATORIO", "QUEIMADA"],
    )
    padrao, resumo = carga.ler_camada(shp)
    assert len(padrao) == 1 and resumo.filtro_classes == ("DESMATAMENTO",)
    todas, _ = carga.ler_camada(shp, classes=None)
    assert len(todas) == 3
    carga.executar(["--arquivo", str(shp), "--bioma", "Cerrado", "--classes", "todas"])
    assert len(_camada()) == 3


def test_zip_com_duas_camadas_exige_escolher(tmp_path):
    yearly = _shapefile_livre(tmp_path, "yearly_deforestation_2026", state=["PA", "AM"], year=[2026, 2026])
    _shapefile_livre(tmp_path, "residual_2026", state=["PA"], year=[2026])
    zipado = tmp_path / "amazonia.zip"
    with zipfile.ZipFile(zipado, "w") as z:
        for parte in tmp_path.glob("*_2026.*"):
            z.write(parte, parte.name)
    with pytest.raises(SystemExit, match="--camada"):
        carga.ler_camada(zipado)
    with pytest.raises(SystemExit, match="não existe"):
        carga.ler_camada(zipado, camada="outra")
    carga.executar(["--arquivo", str(zipado), "--camada", yearly.stem, "--bioma", "Amazonia"])
    assert [(l.bioma, l.uf, l.ano) for l in _camada()] == [("Amazonia", None, 2026), ("Amazonia", None, 2026)]


def test_bioma_inteiro_substitui_as_cargas_por_uf_do_mesmo_bioma(tmp_path):
    shp = _shapefile(tmp_path)  # MG 2021, SP 2023 (2019 fica fora pelo corte)
    carga.executar(["--arquivo", str(shp), "--bioma", "Cerrado", "--uf", "MG"])
    carga.executar(["--arquivo", str(shp), "--bioma", "Pampa", "--uf", "SP"])
    carga.executar(["--arquivo", str(shp), "--bioma", "Cerrado"])  # bioma inteiro
    linhas = [(l.bioma, l.uf, l.ano) for l in _camada()]
    assert linhas == [("Cerrado", None, 2021), ("Cerrado", None, 2023), ("Pampa", "SP", 2023)]
    # carregar uma UF por cima do bioma inteiro duplicaria aquela UF: recusado
    with pytest.raises(SystemExit, match="bioma Cerrado inteiro"):
        carga.executar(["--arquivo", str(shp), "--bioma", "Cerrado", "--uf", "MG"])
    assert len(_camada()) == 3
