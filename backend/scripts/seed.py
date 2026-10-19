#!/usr/bin/env python3
"""
Dados de demonstração: 1 usuário, 2 fornecedores, 4 fazendas e 1 embarque em rascunho.

  - 2 fazendas reais de Adamantina (SICAR) em polígono            → aptas
  - 1 fazenda de até 4 ha em ponto (centro de um imóvel pequeno)  → apta   (exercita R4)
  - 1 fazenda de DEMONSTRAÇÃO sobre o maior polígono do PRODES    → bloqueada
  O embarque nasce com as três aptas; a bloqueada fica de fora para mostrar a recusa (R2).

Pré-requisitos: alembic upgrade head e scripts/carga_prodes.py já executados.

Uso:
  python backend/scripts/seed.py [--arquivo-fazendas data/processed/adamantina_geoJSON.json]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import geopandas as gpd  # noqa: E402
from sqlalchemy import select, text  # noqa: E402

from app.auth import gerar_hash  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import Embarque, Fazenda, Fornecedor, Parcela, Usuario  # noqa: E402
from app.services.geometria import validar_geometria  # noqa: E402
from app.services.verificacao import verificar_fazenda  # noqa: E402

EMAIL = "demo@exemplo.com.br"
SENHA = os.getenv("SEED_SENHA", "demo-origemcheck-2026")


def _nova_fazenda(db, usuario, fornecedor, nome, geometry, **extra) -> Fazenda:
    geom, _ = validar_geometria(db, geometry, extra.get("area_declarada_ha"))
    fazenda = Fazenda(usuario_id=usuario.id, fornecedor_id=fornecedor.id, nome=nome, geom=geom, **extra)
    db.add(fazenda)
    db.flush()
    verificar_fazenda(db, fazenda)
    return fazenda


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--arquivo-fazendas", type=Path, default=Path("data/processed/adamantina_geoJSON.json"))
    args = p.parse_args()

    imoveis = gpd.read_file(args.arquivo_fazendas).set_crs(4326, allow_override=True)
    imoveis = imoveis[imoveis["ind_status"] == "AT"]
    medios = imoveis[(imoveis["num_area"] >= 20) & (imoveis["num_area"] <= 80)].head(2)
    pequeno = imoveis[(imoveis["num_area"] > 0.5) & (imoveis["num_area"] <= 4)].head(1)
    if len(medios) < 2 or pequeno.empty:
        raise SystemExit("Arquivo de fazendas sem imóveis adequados para a demonstração.")

    with SessionLocal() as db:
        if db.scalar(select(Usuario.id).where(Usuario.email == EMAIL)):
            raise SystemExit(f"A demonstração já existe ({EMAIL}). Para refazer, apague o usuário e seus dados.")

        usuario = Usuario(nome="Mariana (demo)", email=EMAIL, senha_hash=gerar_hash(SENHA))
        db.add(usuario)
        db.flush()

        f1 = Fornecedor(usuario_id=usuario.id, nome="Sítio Boa Esperança", documento="52998224725",
                        tipo_pessoa="PF", municipio="Adamantina", uf="SP", email="contato@boaesperanca.com.br")
        f2 = Fornecedor(usuario_id=usuario.id, nome="Cooperativa Cafeeira do Oeste", documento="11222333000181",
                        tipo_pessoa="PJ", municipio="Adamantina", uf="SP")
        db.add_all([f1, f2])
        db.flush()

        def imovel(linha, fornecedor, nome):
            return _nova_fazenda(
                db, usuario, fornecedor, nome, json.loads(gpd.GeoSeries([linha.geometry]).to_json())["features"][0]["geometry"],
                car_codigo=linha["cod_imovel"], municipio=linha["municipio"], uf="SP",
                area_declarada_ha=round(float(linha["num_area"]), 2),
            )

        a = imovel(medios.iloc[0], f1, "Fazenda Boa Esperança")
        b = imovel(medios.iloc[1], f1, "Fazenda Santa Luzia")

        linha = pequeno.iloc[0]
        c = _nova_fazenda(
            db, usuario, f2, "Sítio do Ponto (até 4 ha)",
            {"type": "Point", "coordinates": [linha.geometry.centroid.x, linha.geometry.centroid.y]},
            car_codigo=linha["cod_imovel"], municipio=linha["municipio"], uf="SP",
            area_declarada_ha=round(float(linha["num_area"]), 2),
        )

        # Fazenda de demonstração: envelope do maior polígono de supressão do PRODES (+ ~50 m)
        envelope = db.scalar(
            text(
                "SELECT ST_AsGeoJSON(ST_Envelope(ST_Buffer(geom, 0.0005))) FROM camada_prodes "
                "ORDER BY ST_Area(geom::geography) DESC LIMIT 1"
            )
        )
        if envelope is None:
            raise SystemExit("Camada PRODES vazia. Rode scripts/carga_prodes.py antes do seed.")
        d = _nova_fazenda(db, usuario, f2, "DEMO — sobre área de supressão", json.loads(envelope),
                          car_codigo="DEMO-BLOQUEADA", uf="SP")

        embarque = Embarque(usuario_id=usuario.id, identificacao="EMB-DEMO-001",
                            data_embarque=date(2027, 3, 15), destino="Hamburgo, Alemanha", status="rascunho")
        embarque.parcelas = [
            Parcela(fazenda_id=a.id, quantidade_kg=12000),
            Parcela(fazenda_id=b.id, quantidade_kg=8500),
            Parcela(fazenda_id=c.id, quantidade_kg=900),
        ]
        db.add(embarque)
        db.commit()

        for f in (a, b, c, d):
            print(f"  {f.nome:<34} {f.status:<10} sobreposição {f.area_sobreposta_m2} m²")
        print(f"\nOK. Login: {EMAIL} / {SENHA}")
        print(f"Embarque EMB-DEMO-001 em rascunho com 3 aptas (a bloqueada ficou de fora).")


if __name__ == "__main__":
    main()
