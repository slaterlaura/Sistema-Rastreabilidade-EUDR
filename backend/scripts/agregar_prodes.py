#!/usr/bin/env python3
"""
Recalcula o mapa de calor do desmatamento (tabela prodes_calor) a partir da camada PRODES já carregada.

O carga_prodes.py já faz isso ao fim de cada carga; use este script quando quiser recalcular sem
recarregar o PRODES (por exemplo, logo depois de aplicar a migração 0003 no Azure).

Uso:
  python scripts/agregar_prodes.py
  DATABASE_URL="$DATABASE_URL_AZURE" python scripts/agregar_prodes.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import engine  # noqa: E402
from scripts.comum_carga import atualizar_calor  # noqa: E402


def main() -> None:
    inicio = time.perf_counter()
    with engine.begin() as con:
        pontos = atualizar_calor(con, settings.ano_corte)
        con.execute(text("ANALYZE prodes_calor"))
    for nivel, total in pontos.items():
        print(f"nível {nivel}: {total} pontos")
    print(f"OK: mapa de calor recalculado em {time.perf_counter() - inicio:.1f} s.")


if __name__ == "__main__":
    main()
