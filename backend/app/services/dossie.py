"""Dossiê de origem: retrato congelado (R3), GeoJSON e PDF.

O retrato COPIA os dados do instante do fechamento. Se o PRODES for atualizado depois e uma
fazenda passar a bloqueada, o dossiê de abril não muda: ele é a evidência do que se sabia na época.
"""

import json
from datetime import datetime, timezone
from decimal import Decimal
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import CamadaVersao, Documento, Embarque, Fazenda, Fornecedor, Parcela, Usuario

VERSAO_RETRATO = 1


def _doc_resumo(d: Documento) -> dict:
    return {
        "id": d.id,
        "tipo": d.tipo,
        "nome_arquivo": d.nome_arquivo,
        "sha256": d.sha256,
        "validade": d.validade.isoformat() if d.validade else None,
    }


def _num(valor) -> float | None:
    return None if valor is None else float(valor)


def montar_retrato(db: Session, embarque: Embarque, usuario: Usuario) -> dict:
    linhas = db.execute(
        select(Parcela, Fazenda, Fornecedor, func.ST_AsGeoJSON(Fazenda.geom, 9))
        .join(Fazenda, Fazenda.id == Parcela.fazenda_id)
        .join(Fornecedor, Fornecedor.id == Fazenda.fornecedor_id)
        .where(Parcela.embarque_id == embarque.id)
        .order_by(Parcela.id)
    ).all()

    docs_fornecedor: dict[int, list] = {}
    docs_fazenda: dict[int, list] = {}
    fornecedor_ids = {f.id for _, _, f, _ in linhas}
    fazenda_ids = {fz.id for _, fz, _, _ in linhas}
    if linhas:
        for d in db.scalars(
            select(Documento).where(
                (Documento.fornecedor_id.in_(fornecedor_ids)) | (Documento.fazenda_id.in_(fazenda_ids))
            ).order_by(Documento.id)
        ):
            if d.fornecedor_id:
                docs_fornecedor.setdefault(d.fornecedor_id, []).append(_doc_resumo(d))
            else:
                docs_fazenda.setdefault(d.fazenda_id, []).append(_doc_resumo(d))

    versao_ids = {fz.camada_versao_id for _, fz, _, _ in linhas if fz.camada_versao_id}
    camadas = [
        {
            "id": v.id,
            "origem": v.origem,
            "bioma": v.bioma,
            "uf": v.uf,
            "arquivo": v.arquivo,
            "n_feicoes": v.n_feicoes,
            "carregada_em": v.carregada_em.isoformat(),
        }
        for v in db.scalars(select(CamadaVersao).where(CamadaVersao.id.in_(versao_ids)).order_by(CamadaVersao.id))
    ]

    parcelas = []
    for parcela, fazenda, fornecedor, geojson in linhas:
        parcelas.append(
            {
                "parcela_id": parcela.id,
                "quantidade_kg": _num(parcela.quantidade_kg),
                "observacao": parcela.observacao,
                "fazenda": {
                    "id": fazenda.id,
                    "nome": fazenda.nome,
                    "car_codigo": fazenda.car_codigo,
                    "ccir": fazenda.ccir,
                    "nirf": fazenda.nirf,
                    "matricula": fazenda.matricula,
                    "municipio": fazenda.municipio,
                    "uf": fazenda.uf,
                    "area_declarada_ha": _num(fazenda.area_declarada_ha),
                    "status": fazenda.status,
                    "area_sobreposta_m2": _num(fazenda.area_sobreposta_m2),
                    "verificada_em": fazenda.verificada_em.isoformat() if fazenda.verificada_em else None,
                    "camada_versao_id": fazenda.camada_versao_id,
                    "geometry": json.loads(geojson),
                    "documentos": docs_fazenda.get(fazenda.id, []),
                },
                "fornecedor": {
                    "id": fornecedor.id,
                    "nome": fornecedor.nome,
                    "documento": fornecedor.documento,
                    "tipo_pessoa": fornecedor.tipo_pessoa,
                    "documentos": docs_fornecedor.get(fornecedor.id, []),
                },
            }
        )

    return {
        "versao_retrato": VERSAO_RETRATO,
        "gerado_em": datetime.now(timezone.utc).isoformat(),
        "exportador": {"nome": usuario.nome, "email": usuario.email},
        "embarque": {
            "id": embarque.id,
            "identificacao": embarque.identificacao,
            "data_embarque": embarque.data_embarque.isoformat(),
            "destino": embarque.destino,
        },
        "criterios": {
            "data_corte_desmatamento": f"{settings.ano_corte}-12-31",
            "tolerancia_m2": settings.tolerancia_m2,
            "observacao": (
                "Fazendas em ponto (até 4 ha) são avaliadas de forma binária: bloqueiam se o ponto cai "
                "dentro de uma área de supressão. Fazendas em polígono bloqueiam quando a área sobreposta "
                "atinge a tolerância."
            ),
        },
        "camadas_referencia": camadas,
        "total_kg": float(sum(Decimal(str(p["quantidade_kg"])) for p in parcelas)),
        "parcelas": parcelas,
    }


def montar_geojson(retrato: dict) -> dict:
    """FeatureCollection processável por sistema (prioridade do importador, que não usa o app)."""
    features = []
    for p in retrato["parcelas"]:
        f, forn = p["fazenda"], p["fornecedor"]
        features.append(
            {
                "type": "Feature",
                "geometry": f["geometry"],
                "properties": {
                    "fazenda_id": f["id"],
                    "fazenda": f["nome"],
                    "car_codigo": f["car_codigo"],
                    "municipio": f["municipio"],
                    "uf": f["uf"],
                    "fornecedor": forn["nome"],
                    "fornecedor_documento": forn["documento"],
                    "quantidade_kg": p["quantidade_kg"],
                    "status": f["status"],
                    "area_sobreposta_m2": f["area_sobreposta_m2"],
                    "verificada_em": f["verificada_em"],
                    "camada_versao_id": f["camada_versao_id"],
                },
            }
        )
    return {
        "type": "FeatureCollection",
        "name": f"dossie-{retrato['embarque']['identificacao']}",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
        "embarque": retrato["embarque"],
        "criterios": retrato["criterios"],
        "camadas_referencia": retrato["camadas_referencia"],
        "features": features,
    }


def _fmt_data(iso: str | None) -> str:
    if not iso:
        return "—"
    return datetime.fromisoformat(iso).strftime("%d/%m/%Y %H:%M")


def _kg(v: float) -> str:
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def montar_pdf(retrato: dict) -> bytes:
    estilos = getSampleStyleSheet()
    pequeno = ParagraphStyle("pequeno", parent=estilos["BodyText"], fontSize=8, leading=10)
    normal = ParagraphStyle("normal", parent=estilos["BodyText"], fontSize=9.5, leading=12)
    emb = retrato["embarque"]

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm,
        title=f"Dossiê de origem — {emb['identificacao']}", author="OrigemCheck",
    )
    h = []
    h.append(Paragraph("Dossiê de origem — EUDR", estilos["Title"]))
    h.append(Paragraph(f"Embarque <b>{emb['identificacao']}</b> · destino {emb['destino']} · "
                       f"data {datetime.fromisoformat(emb['data_embarque']).strftime('%d/%m/%Y')}", normal))
    h.append(Paragraph(f"Exportador: {retrato['exportador']['nome']} ({retrato['exportador']['email']}) · "
                       f"gerado em {_fmt_data(retrato['gerado_em'])}", normal))
    h.append(Paragraph(f"Quantidade total: <b>{_kg(retrato['total_kg'])} kg</b> em {len(retrato['parcelas'])} parcela(s)", normal))
    h.append(Spacer(1, 10))

    h.append(Paragraph("Critérios da verificação", estilos["Heading3"]))
    c = retrato["criterios"]
    h.append(Paragraph(f"Data de corte: {datetime.fromisoformat(c['data_corte_desmatamento']).strftime('%d/%m/%Y')}. "
                       f"Tolerância de sobreposição: {c['tolerancia_m2']:.0f} m². {c['observacao']}", pequeno))
    for camada in retrato["camadas_referencia"]:
        h.append(Paragraph(f"Camada de referência #{camada['id']}: {camada['origem']} — {camada['bioma']}"
                           f"{'/' + camada['uf'] if camada['uf'] else ''}, {camada['n_feicoes']} feições, "
                           f"carregada em {_fmt_data(camada['carregada_em'])}.", pequeno))
    h.append(Spacer(1, 10))

    h.append(Paragraph("Parcelas", estilos["Heading3"]))
    cab = ["Fazenda / CAR", "Fornecedor", "Qtd. (kg)", "Status", "Sobreposição (ha)"]
    linhas = [cab]
    for p in retrato["parcelas"]:
        f, forn = p["fazenda"], p["fornecedor"]
        linhas.append([
            Paragraph(f"{f['nome']}<br/><font size=7>{f['car_codigo'] or 'CAR não informado'}</font>", pequeno),
            Paragraph(f"{forn['nome']}<br/><font size=7>{forn['documento']}</font>", pequeno),
            _kg(p["quantidade_kg"]),
            f["status"].upper(),
            f"{(f['area_sobreposta_m2'] or 0) / 10000:.4f}".replace(".", ","),
        ])
    tabela = Table(linhas, colWidths=[5.2 * cm, 4.4 * cm, 2.4 * cm, 2.0 * cm, 3.0 * cm], repeatRows=1)
    tabela.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f3a2e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
        ("ALIGN", (2, 1), (2, -1), "RIGHT"),
        ("ALIGN", (4, 1), (4, -1), "RIGHT"),
    ]))
    h.append(tabela)
    h.append(Spacer(1, 12))

    h.append(Paragraph("Detalhe por fazenda", estilos["Heading3"]))
    for p in retrato["parcelas"]:
        f = p["fazenda"]
        g = f["geometry"]
        tipo = "Ponto" if g["type"] == "Point" else "Polígono"
        h.append(Paragraph(f"<b>{f['nome']}</b> — {f['municipio'] or '—'}/{f['uf'] or '—'}", normal))
        h.append(Paragraph(
            f"Geometria: {tipo} · área declarada: {f['area_declarada_ha'] or '—'} ha · "
            f"CCIR: {f['ccir'] or '—'} · NIRF: {f['nirf'] or '—'} · matrícula: {f['matricula'] or '—'}<br/>"
            f"Verificada em {_fmt_data(f['verificada_em'])} (camada #{f['camada_versao_id']}) — "
            f"<b>{f['status'].upper()}</b>, sobreposição {f['area_sobreposta_m2'] or 0:.2f} m².", pequeno))
        docs = f["documentos"] + p["fornecedor"]["documentos"]
        if docs:
            for d in docs:
                h.append(Paragraph(f"• {d['tipo'].upper()}: {d['nome_arquivo']} · SHA-256 {d['sha256'][:16]}…"
                                   f"{' · validade ' + d['validade'] if d['validade'] else ''}", pequeno))
        else:
            h.append(Paragraph("• Nenhum documento anexado.", pequeno))
        h.append(Spacer(1, 6))

    h.append(Spacer(1, 8))
    h.append(Paragraph("Este dossiê é um retrato fixo do momento do fechamento do embarque. "
                       "As geometrias completas estão no arquivo GeoJSON que o acompanha.", pequeno))
    doc.build(h)
    return buffer.getvalue()
