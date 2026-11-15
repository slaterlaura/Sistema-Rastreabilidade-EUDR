#!/usr/bin/env python3
"""
Fazendas de demonstração a partir da camada de imóveis do CAR (PE, MA e RS por padrão).

Imóvel do CAR é só referência: não tem fornecedor, status nem entra em embarque. Este script faz o que um
exportador faria na tela "Nova fazenda → usar imóvel do CAR", para a demonstração ter fazendas desses estados
iguais às de Adamantina. Por estado:
  - 1 fornecedor fictício;
  - 2 imóveis ativos de 20 a 80 ha sem supressão PRODES pós-corte      → aptas;
  - 1 imóvel ativo de 20 a 200 ha com supressão acima da tolerância    → bloqueada (sobreposição real).
E um embarque em rascunho (EMB-DEMO-002) com as aptas.

A escolha é determinística (ordem do código do CAR) e o script pode rodar de novo: o que já existe é pulado.

Pré-requisitos: scripts/seed.py (usuário demo), PRODES e imóveis carregados.

Uso:
  python scripts/seed_imoveis.py                 # PE, MA e RS
  python scripts/seed_imoveis.py --ufs SP        # outros estados
  DATABASE_URL="$DATABASE_URL_AZURE" python scripts/seed_imoveis.py
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import select, text  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import Embarque, Fazenda, Fornecedor, Parcela, Usuario  # noqa: E402
from scripts.seed import EMAIL, _nova_fazenda  # noqa: E402

NOMES_UF = {"PE": "Pernambuco", "MA": "Maranhão", "RS": "Rio Grande do Sul"}
APTAS_POR_UF = 2
EMBARQUE = "EMB-DEMO-002"

_SQL_SUPRESSAO = """
    (SELECT coalesce(sum(ST_Area(ST_Intersection(ST_MakeValid(i.geom), p.geom)::geography)), 0)
     FROM camada_prodes p
     WHERE p.geom && i.geom AND p.ano > :corte AND ST_Intersects(ST_MakeValid(i.geom), p.geom))
"""

_SQL_APTAS = text(
    """
    SELECT i.cod_imovel, i.municipio, i.area_ha, ST_AsGeoJSON(i.geom) AS geojson
    FROM imovel i
    WHERE i.uf = :uf AND i.situacao = 'AT' AND i.area_ha BETWEEN 20 AND 80
      AND NOT EXISTS (SELECT 1 FROM camada_prodes p WHERE p.geom && i.geom AND p.ano > :corte)
    ORDER BY i.cod_imovel
    LIMIT :limite
    """
)

_SQL_BLOQUEADAS = text(
    f"""
    SELECT i.cod_imovel, i.municipio, i.area_ha, ST_AsGeoJSON(i.geom) AS geojson
    FROM imovel i
    WHERE i.uf = :uf AND i.situacao = 'AT' AND i.area_ha BETWEEN 20 AND 200
      AND EXISTS (SELECT 1 FROM camada_prodes p WHERE p.geom && i.geom AND p.ano > :corte)
      AND {_SQL_SUPRESSAO} >= :tol
    ORDER BY i.cod_imovel
    LIMIT :limite
    """
)


def cnpj_demo(base: str) -> str:
    """CNPJ com dígitos verificadores válidos a partir de 12 dígitos (dados fictícios)."""
    def digito(numeros: str) -> str:
        pesos = list(range(len(numeros) - 7, 1, -1)) + list(range(9, 1, -1))
        resto = sum(int(n) * p for n, p in zip(numeros, pesos)) % 11
        return "0" if resto < 2 else str(11 - resto)

    d1 = digito(base)
    return base + d1 + digito(base + d1)


_MINUSCULAS = {"e", "da", "de", "do", "das", "dos"}


def _municipio(nome: str | None, uf: str) -> str:
    """'ABREU E LIMA' -> 'Abreu e Lima' (o SICAR traz caixa alta e, às vezes, sem acento)."""
    if not nome:
        return NOMES_UF.get(uf, uf)
    palavras = nome.lower().split()
    return " ".join(p if i and p in _MINUSCULAS else p.capitalize() for i, p in enumerate(palavras))


def _fornecedor(db, usuario: Usuario, uf: str) -> Fornecedor:
    documento = cnpj_demo(f"90{ord(uf[0]):02d}{ord(uf[1]):02d}000001")  # fixo por UF: rodar de novo acha o mesmo
    existente = db.scalar(
        select(Fornecedor).where(Fornecedor.usuario_id == usuario.id, Fornecedor.documento == documento)
    )
    if existente:
        return existente
    fornecedor = Fornecedor(
        usuario_id=usuario.id, nome=f"Cooperativa Demo {NOMES_UF.get(uf, uf)}", documento=documento,
        tipo_pessoa="PJ", uf=uf,
    )
    db.add(fornecedor)
    db.flush()
    return fornecedor


def _adotar(db, usuario, fornecedor, uf, sql, quantas, nome, esperado, ja_cadastrados) -> list[Fazenda]:
    """Cadastra até `quantas` fazendas a partir dos candidatos; pula imóveis com geometria que não passa."""
    criadas = []
    candidatos = db.execute(
        sql, {"uf": uf, "corte": settings.ano_corte, "tol": settings.tolerancia_m2, "limite": quantas + 10}
    ).all()
    for linha in candidatos:
        if len(criadas) == quantas:
            break
        if linha.cod_imovel in ja_cadastrados:
            continue
        municipio = _municipio(linha.municipio, uf)
        try:
            with db.begin_nested():
                fazenda = _nova_fazenda(
                    db, usuario, fornecedor, nome(municipio, len(criadas) + 1), json.loads(linha.geojson),
                    car_codigo=linha.cod_imovel, municipio=municipio, uf=uf,
                    area_declarada_ha=round(float(linha.area_ha), 2),
                )
                if fazenda.status != esperado:
                    raise ValueError("status diferente do esperado")
        except (HTTPException, ValueError):
            continue
        criadas.append(fazenda)
    return criadas


def executar(argv: list[str] | None = None) -> list[Fazenda]:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ufs", default="PE,MA,RS", help="estados, separados por vírgula (padrão: PE,MA,RS)")
    args = p.parse_args(argv)
    ufs = [u.strip().upper() for u in args.ufs.split(",") if u.strip()]

    with SessionLocal() as db:
        usuario = db.scalar(select(Usuario).where(Usuario.email == EMAIL))
        if usuario is None:
            raise SystemExit(f"Usuário de demonstração ({EMAIL}) não existe. Rode scripts/seed.py antes.")

        if not db.scalar(text("SELECT EXISTS (SELECT 1 FROM camada_prodes WHERE ano > :c)"), {"c": settings.ano_corte}):
            raise SystemExit("Camada PRODES vazia. Rode scripts/carga_prodes.py antes.")

        # CAR é único por usuário: inclui os de Adamantina e de outros fornecedores
        ja = set(db.scalars(select(Fazenda.car_codigo).where(Fazenda.usuario_id == usuario.id)))
        novas: list[Fazenda] = []
        aptas_embarque: list[Fazenda] = []
        for uf in ufs:
            if not db.scalar(text("SELECT EXISTS (SELECT 1 FROM imovel WHERE uf = :uf)"), {"uf": uf}):
                print(f"  {uf}: sem imóveis carregados, pulando.")
                continue
            fornecedor = _fornecedor(db, usuario, uf)
            existentes = db.scalars(select(Fazenda).where(Fazenda.fornecedor_id == fornecedor.id)).all()
            aptas = [f for f in existentes if f.status == "apta"]
            bloqueadas = [f for f in existentes if f.status == "bloqueada"]

            aptas_novas = _adotar(
                db, usuario, fornecedor, uf, _SQL_APTAS, max(0, APTAS_POR_UF - len(aptas)),
                lambda m, n: f"Fazenda {m} {len(aptas) + n}", "apta", ja,
            )
            bloqueadas_novas = _adotar(
                db, usuario, fornecedor, uf, _SQL_BLOQUEADAS, max(0, 1 - len(bloqueadas)),
                lambda m, n: f"Fazenda {m} (supressão)", "bloqueada", ja,
            )
            novas += aptas_novas + bloqueadas_novas
            ja |= {f.car_codigo for f in aptas_novas + bloqueadas_novas}
            aptas_embarque += aptas + aptas_novas
            if len(aptas + aptas_novas) < APTAS_POR_UF or not (bloqueadas or bloqueadas_novas):
                print(f"  {uf}: não achei imóveis suficientes (aptas e/ou bloqueada).")

        if aptas_embarque and not db.scalar(
            select(Embarque.id).where(Embarque.usuario_id == usuario.id, Embarque.identificacao == EMBARQUE)
        ):
            embarque = Embarque(usuario_id=usuario.id, identificacao=EMBARQUE, data_embarque=date(2027, 5, 20),
                                destino="Roterdã, Países Baixos", status="rascunho")
            embarque.parcelas = [Parcela(fazenda_id=f.id, quantidade_kg=6000) for f in aptas_embarque]
            db.add(embarque)
        db.commit()

        for f in novas:
            print(f"  {f.uf}  {f.nome:<40} {f.status:<10} sobreposição {f.area_sobreposta_m2} m²")
        print(f"\nOK: {len(novas)} fazendas novas" + ("" if novas else " (a demonstração já estava completa)") + ".")
        return novas


if __name__ == "__main__":
    executar()
