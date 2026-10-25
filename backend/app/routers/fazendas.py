import json

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import usuario_atual
from app.database import get_db
from app.models import Fazenda, Usuario
from app.routers.fornecedores import obter_fornecedor
from app.schemas import FazendaIn, FazendaOut, FazendaUpdate, ImportarGeoJSONIn
from app.services.arquivos import apagar_arquivos, caminhos_documentos
from app.services.geometria import validar_geometria
from app.services.verificacao import verificar_fazenda

router = APIRouter(prefix="/fazendas", tags=["fazendas"])

_GEOJSON = func.ST_AsGeoJSON(Fazenda.geom, 9)


def _saida(fazenda: Fazenda, geojson: str) -> FazendaOut:
    campos = {c: getattr(fazenda, c) for c in FazendaOut.model_fields if c != "geometry"}
    return FazendaOut(**campos, geometry=json.loads(geojson))


def _carregar(db: Session, usuario: Usuario, fazenda_id: int) -> tuple[Fazenda, str]:
    """R6: fazenda de outro usuário devolve 404."""
    linha = db.execute(
        select(Fazenda, _GEOJSON).where(Fazenda.id == fazenda_id, Fazenda.usuario_id == usuario.id)
    ).first()
    if linha is None:
        raise HTTPException(404, detail="Fazenda não encontrada.")
    return linha[0], linha[1]


def obter_fazenda(db: Session, usuario: Usuario, fazenda_id: int) -> Fazenda:
    return _carregar(db, usuario, fazenda_id)[0]


def _conflito(exc: IntegrityError) -> HTTPException:
    if "uq_fazenda_usuario_car" in str(exc.orig):
        return HTTPException(409, detail="Já existe uma fazenda com este código CAR na sua conta.")
    return HTTPException(409, detail=f"Conflito ao salvar a fazenda: {exc.orig}")


def _criar(db: Session, usuario: Usuario, dados: FazendaIn) -> Fazenda:
    obter_fornecedor(db, usuario, dados.fornecedor_id)
    geom, _ = validar_geometria(db, dados.geometry, dados.area_declarada_ha)
    fazenda = Fazenda(
        **dados.model_dump(exclude={"geometry"}), usuario_id=usuario.id, geom=geom, status="pendente"
    )
    db.add(fazenda)
    db.flush()
    verificar_fazenda(db, fazenda)  # R1: salvar e verificar na mesma transação
    return fazenda


@router.get("", response_model=list[FazendaOut])
def listar(
    fornecedor_id: int | None = None,
    status: str | None = Query(default=None, pattern="^(pendente|apta|bloqueada)$"),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_atual),
):
    consulta = select(Fazenda, _GEOJSON).where(Fazenda.usuario_id == usuario.id).order_by(Fazenda.id)
    if fornecedor_id is not None:
        consulta = consulta.where(Fazenda.fornecedor_id == fornecedor_id)
    if status:
        consulta = consulta.where(Fazenda.status == status)
    return [_saida(f, g) for f, g in db.execute(consulta)]


@router.post("", response_model=FazendaOut, status_code=201)
def criar(dados: FazendaIn, db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    try:
        fazenda = _criar(db, usuario, dados)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _conflito(exc)
    except HTTPException:
        db.rollback()
        raise
    return _saida(*_carregar(db, usuario, fazenda.id))


@router.post("/import-geojson", status_code=201)
def importar_geojson(
    dados: ImportarGeoJSONIn, db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_atual)
):
    """Importa um FeatureCollection; tudo ou nada. Cada fazenda é verificada ao salvar."""
    obter_fornecedor(db, usuario, dados.fornecedor_id)
    if dados.geojson.get("type") != "FeatureCollection":
        raise HTTPException(400, detail="O GeoJSON deve ser um FeatureCollection.")
    features = dados.geojson.get("features")
    if not isinstance(features, list) or not features:
        raise HTTPException(400, detail="O GeoJSON não tem feições para importar.")

    criadas = []
    try:
        for i, feature in enumerate(features):
            props = (feature or {}).get("properties") or {}
            rotulo = props.get(dados.prop_nome) or f"Fazenda importada {i + 1}"
            area = props.get(dados.prop_area_ha)
            try:
                entrada = FazendaIn(
                    fornecedor_id=dados.fornecedor_id,
                    nome=str(rotulo)[:255],
                    car_codigo=props.get(dados.prop_car),
                    municipio=props.get(dados.prop_municipio),
                    area_declarada_ha=area if area and float(area) > 0 else None,
                    geometry=feature.get("geometry") or {},
                )
                fazenda = _criar(db, usuario, entrada)
            except HTTPException as exc:
                raise HTTPException(400, detail=f"Feição {i} ({rotulo}): {exc.detail}")
            except ValueError as exc:
                raise HTTPException(400, detail=f"Feição {i} ({rotulo}): dados inválidos ({exc}).")
            criadas.append(fazenda)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _conflito(exc)
    except HTTPException:
        db.rollback()
        raise

    resumo = {"apta": 0, "bloqueada": 0}
    for f in criadas:
        resumo[f.status] += 1
    return {"importadas": len(criadas), "resumo": resumo, "fazenda_ids": [f.id for f in criadas]}


@router.post("/reverificar")
def reverificar_todas(db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    """Reprocessamento manual, para quando a camada de referência for atualizada."""
    fazendas = db.scalars(select(Fazenda).where(Fazenda.usuario_id == usuario.id)).all()
    mudancas = []
    for f in fazendas:
        antes = f.status
        verificar_fazenda(db, f)
        if f.status != antes:
            mudancas.append({"fazenda_id": f.id, "nome": f.nome, "de": antes, "para": f.status})
    db.commit()
    return {"verificadas": len(fazendas), "mudaram_de_status": mudancas}


@router.get("/{fazenda_id}", response_model=FazendaOut)
def detalhar(fazenda_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    return _saida(*_carregar(db, usuario, fazenda_id))


@router.put("/{fazenda_id}", response_model=FazendaOut)
def atualizar(
    fazenda_id: int,
    dados: FazendaUpdate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(usuario_atual),
):
    fazenda, geojson_atual = _carregar(db, usuario, fazenda_id)
    campos = dados.model_dump(exclude_unset=True)
    if not campos:
        raise HTTPException(400, detail="Nenhum campo para atualizar.")

    try:
        refazer = "geometry" in campos or "area_declarada_ha" in campos
        if refazer:
            area = campos.get("area_declarada_ha", fazenda.area_declarada_ha)
            geometria = campos.pop("geometry", None) or json.loads(geojson_atual)
            fazenda.geom, _ = validar_geometria(db, geometria, area)
        for campo, valor in campos.items():
            setattr(fazenda, campo, valor)
        if refazer:
            verificar_fazenda(db, fazenda)  # R1: mudou a geometria, reverifica
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _conflito(exc)
    except HTTPException:
        db.rollback()
        raise
    return _saida(*_carregar(db, usuario, fazenda_id))


@router.post("/{fazenda_id}/verificar", response_model=FazendaOut)
def verificar(fazenda_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    fazenda = obter_fazenda(db, usuario, fazenda_id)
    verificar_fazenda(db, fazenda)
    db.commit()
    return _saida(*_carregar(db, usuario, fazenda_id))


@router.delete("/{fazenda_id}", status_code=204)
def excluir(fazenda_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    fazenda = obter_fazenda(db, usuario, fazenda_id)
    caminhos = caminhos_documentos(db, fazenda_id=fazenda.id)
    db.delete(fazenda)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, detail="Esta fazenda faz parte de um embarque e não pode ser excluída.")
    apagar_arquivos(caminhos)
    return Response(status_code=204)
