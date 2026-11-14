/**
 * Peças de mapa (Leaflet) do quadro de fazendas.
 *
 * - Camada de supressão do PRODES por baixo, hachurada e desligável (context.md §13).
 * - Fazenda em polígono: cor do traço = status. Fazenda em ponto: círculo cheio com anel tracejado,
 *   para deixar claro que não há área delimitada.
 */

import { useQuery } from "@tanstack/react-query";
import L from "leaflet";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import {
  CircleMarker,
  GeoJSON,
  LayersControl,
  MapContainer,
  Pane,
  TileLayer,
  Tooltip,
  useMap,
  useMapEvents,
} from "react-leaflet";
import { api } from "@/lib/api";
import { CENTRO_PADRAO, limitesDe } from "@/lib/geo";
import { COR_DESTAQUE, COR_SUPRESSAO, STATUS } from "@/lib/status";
import type { CamadaImovel, CamadaSupressao as Camada, GeometriaFazenda, ImovelResumo, StatusFazenda } from "@/lib/tipos";
import { cn } from "@/lib/utils";

/** Padrão SVG referenciado pela camada de supressão (fill: url(#hachura-supressao)). */
export function DefinicoesHachura() {
  return (
    <svg width="0" height="0" aria-hidden="true" className="absolute">
      <defs>
        <pattern id="hachura-supressao" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <rect width="7" height="7" fill={COR_SUPRESSAO} fillOpacity="0.08" />
          <line x1="0" y1="0" x2="0" y2="7" stroke={COR_SUPRESSAO} strokeWidth="2.2" strokeOpacity="0.55" />
        </pattern>
      </defs>
    </svg>
  );
}

interface MapaProps {
  className?: string;
  children?: ReactNode;
  zoomInicial?: number;
}

/** Mapa base: fundo claro por padrão, satélite para desenhar sobre a lavoura. */
export function Mapa({ className, children, zoomInicial = 4 }: MapaProps) {
  return (
    <MapContainer
      center={CENTRO_PADRAO}
      zoom={zoomInicial}
      scrollWheelZoom
      maxZoom={19}
      className={cn("h-full w-full", className)}
      attributionControl
    >
      <LayersControl position="topright">
        <LayersControl.BaseLayer checked name="Mapa claro">
          <TileLayer
            url="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}"
            attribution="Base &copy; Esri, HERE, Garmin, &copy; colaboradores do OpenStreetMap"
            maxZoom={16}
          />
        </LayersControl.BaseLayer>
        <LayersControl.BaseLayer name="Ruas (OpenStreetMap)">
          <TileLayer
            url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">colaboradores do OpenStreetMap</a>'
            maxZoom={19}
          />
        </LayersControl.BaseLayer>
        <LayersControl.BaseLayer name="Satélite">
          <TileLayer
            url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
            attribution="Imagens &copy; Esri, Maxar, Earthstar Geographics"
            maxZoom={19}
          />
        </LayersControl.BaseLayer>
      </LayersControl>
      <Pane name="supressao" style={{ zIndex: 350 }} />
      <Pane name="imoveis" style={{ zIndex: 360 }} />
      {children}
    </MapContainer>
  );
}

export interface EstadoCamada {
  carregando: boolean;
  aproximar: boolean;
  truncado: boolean;
  erro: string | null;
}

export interface VersaoCamada {
  versao: number | null;
  atualizada_em: string | null;
  biomas: string[];
  imoveis_versao: number | null;
}

/** Uma consulta por sessão (5 min); "Reprocessar camada" a invalida. */
export function useVersaoCamada(habilitada = true) {
  return useQuery({
    queryKey: ["camada-versao"],
    queryFn: () => api.get<VersaoCamada>("/camada/versao"),
    enabled: habilitada,
    staleTime: 5 * 60 * 1000,
  });
}

function recorteArredondado(mapa: L.Map, passo: number): string {
  const b = mapa.getBounds();
  const baixo = (v: number) => Math.floor(v / passo) * passo;
  const alto = (v: number) => Math.ceil(v / passo) * passo;
  return [baixo(b.getWest()), baixo(b.getSouth()), alto(b.getEast()), alto(b.getNorth())]
    .map((v) => v.toFixed(2))
    .join(",");
}

/**
 * Busca uma camada de referência só no recorte visível e só com zoom suficiente.
 * Cada busca é uma execução da Function: o recorte é arredondado numa grade (recortes iguais vêm do
 * cache), o mapa não consulta nada enquanto está afastado, e a versão da carga vai na URL para o
 * navegador não reaproveitar dados de uma carga antiga.
 */
function useCamadaRecortada<T extends { truncado: boolean }>(opcoes: {
  chave: string;
  rota: string;
  zoomMinimo: number;
  passo: number;
  visivel: boolean;
  versaoDe: (v: VersaoCamada) => number | null;
  onEstado?: (estado: EstadoCamada) => void;
}) {
  const { chave, rota, zoomMinimo, passo, visivel, versaoDe, onEstado } = opcoes;
  const mapa = useMap();
  const [vista, setVista] = useState(() => ({ zoom: mapa.getZoom(), recorte: recorteArredondado(mapa, passo) }));
  const temporizador = useRef<number>();

  const lerVista = useCallback(() => {
    window.clearTimeout(temporizador.current);
    temporizador.current = window.setTimeout(
      () => setVista({ zoom: mapa.getZoom(), recorte: recorteArredondado(mapa, passo) }),
      350,
    );
  }, [mapa, passo]);

  useMapEvents({ moveend: lerVista });

  // O mapa costuma ser enquadrado (fitBounds) antes deste componente começar a ouvir eventos;
  // relê a vista depois de montado para não ficar preso ao recorte inicial.
  useEffect(() => {
    lerVista();
    return () => window.clearTimeout(temporizador.current);
  }, [lerVista]);

  const habilitada = visivel && vista.zoom >= zoomMinimo;
  const { data: versao } = useVersaoCamada(visivel);
  const v = versao ? (versaoDe(versao) ?? 0) : 0;
  const { data, isFetching, error } = useQuery({
    queryKey: [chave, v, vista.recorte],
    queryFn: () => api.get<T>(`${rota}?bbox=${vista.recorte}&v=${v}`),
    enabled: habilitada && versao !== undefined,
    staleTime: Infinity,
    gcTime: 30 * 60 * 1000,
    placeholderData: (anterior) => anterior,
  });

  useEffect(() => {
    onEstado?.({
      carregando: habilitada && isFetching,
      aproximar: visivel && vista.zoom < zoomMinimo,
      truncado: Boolean(habilitada && data?.truncado),
      erro: error ? (error as Error).message : null,
    });
  }, [onEstado, habilitada, isFetching, visivel, vista.zoom, zoomMinimo, data?.truncado, error]);

  return { data: habilitada ? data : undefined, chaveRender: `${v}-${vista.recorte}-${data ? 1 : 0}` };
}

/** Supressão do PRODES posterior à data de corte, hachurada, por baixo das fazendas. */
export function CamadaSupressao({ visivel, onEstado }: { visivel: boolean; onEstado?: (estado: EstadoCamada) => void }) {
  const { data, chaveRender } = useCamadaRecortada<Camada>({
    chave: "camada-prodes",
    rota: "/camada/prodes",
    zoomMinimo: 10,
    passo: 0.25,
    visivel,
    versaoDe: (v) => v.versao,
    onEstado,
  });
  if (!data) return null;
  return (
    <GeoJSON
      key={`${chaveRender}-${data.features.length}`}
      data={data as GeoJSON.FeatureCollection}
      pane="supressao"
      interactive={false}
      style={() => ({ color: COR_SUPRESSAO, weight: 0.8, opacity: 0.7, className: "supressao-hachura" })}
    />
  );
}

/**
 * Imóveis do CAR (camada comum a todos), em contorno cinza fino.
 * Com onSelecionar, cada imóvel fica clicável (para adotá-lo como fazenda).
 */
export function CamadaImoveis({
  visivel,
  onEstado,
  onSelecionar,
  selecionado,
}: {
  visivel: boolean;
  onEstado?: (estado: EstadoCamada) => void;
  onSelecionar?: (imovel: ImovelResumo) => void;
  selecionado?: string | null;
}) {
  const { data, chaveRender } = useCamadaRecortada<CamadaImovel>({
    chave: "camada-imoveis",
    rota: "/imoveis",
    zoomMinimo: 12,
    passo: 0.1,
    visivel,
    versaoDe: (v) => v.imoveis_versao,
    onEstado,
  });
  if (!data) return null;
  const clicavel = Boolean(onSelecionar);
  return (
    <GeoJSON
      key={`${chaveRender}-${data.features.length}-${selecionado ?? ""}-${clicavel}`}
      data={data as GeoJSON.FeatureCollection}
      pane="imoveis"
      interactive={clicavel}
      style={(f) => {
        const ativo = f?.properties?.cod_imovel === selecionado;
        return {
          color: ativo ? COR_DESTAQUE : "#475569",
          weight: ativo ? 2.5 : 0.9,
          opacity: ativo ? 1 : 0.75,
          fill: clicavel,
          fillColor: ativo ? COR_DESTAQUE : "#94a3b8",
          fillOpacity: ativo ? 0.18 : clicavel ? 0.04 : 0,
        };
      }}
      onEachFeature={(feature, camada) => {
        const p = feature.properties as ImovelResumo;
        const area = p.area_ha != null ? ` · ${p.area_ha.toLocaleString("pt-BR", { maximumFractionDigits: 1 })} ha` : "";
        camada.bindTooltip(`<span class="font-mono text-[11px]">${p.cod_imovel}${area}</span>`, { sticky: true });
        if (onSelecionar) camada.on("click", () => onSelecionar(p));
      }}
    />
  );
}

interface GeometriaProps {
  geometria: GeometriaFazenda;
  status: StatusFazenda;
  rotulo?: string;
  selecionada?: boolean;
  esmaecida?: boolean;
  onClick?: () => void;
}

/** Desenha uma fazenda; a cor do traço é o status. */
export function GeometriaFazendaMapa({ geometria, status, rotulo, selecionada, esmaecida, onClick }: GeometriaProps) {
  const estilo = STATUS[status];
  const cor = estilo.cor;
  const opacidade = esmaecida ? 0.45 : 1;
  const eventos = onClick ? { click: onClick } : undefined;
  const dica = rotulo ? (
    <Tooltip direction="top" sticky>
      <span className="font-mono text-[11px]">{rotulo}</span>
    </Tooltip>
  ) : null;

  if (geometria.type === "Point") {
    const [lng, lat] = geometria.coordinates;
    return (
      <>
        <CircleMarker
          center={[lat, lng]}
          radius={selecionada ? 13 : 11}
          pathOptions={{ color: selecionada ? COR_DESTAQUE : cor, weight: 1.5, dashArray: "3 4", fill: false, opacity: opacidade }}
          interactive={false}
        />
        <CircleMarker
          center={[lat, lng]}
          radius={5}
          pathOptions={{ color: "#ffffff", weight: 1.5, fillColor: cor, fillOpacity: opacidade, opacity: opacidade }}
          eventHandlers={eventos}
        >
          {dica}
        </CircleMarker>
      </>
    );
  }

  return (
    <GeoJSON
      key={`${status}-${selecionada}-${esmaecida}`}
      data={geometria}
      eventHandlers={eventos}
      style={() => ({
        color: selecionada ? COR_DESTAQUE : cor,
        weight: selecionada ? 3 : 1.6,
        dashArray: estilo.traco,
        opacity: opacidade,
        fillColor: cor,
        fillOpacity: selecionada ? 0.28 : esmaecida ? 0.06 : 0.14,
      })}
    >
      {dica}
    </GeoJSON>
  );
}

/** Enquadra o mapa nas geometrias quando a chave muda (não a cada render). */
export function Enquadrar({ geometrias, chave, zoomMaximo = 15 }: { geometrias: GeometriaFazenda[]; chave: string; zoomMaximo?: number }) {
  const mapa = useMap();
  useEffect(() => {
    const limites = limitesDe(geometrias);
    if (limites) mapa.fitBounds(limites, { padding: [32, 32], maxZoom: zoomMaximo });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chave, mapa]);
  return null;
}

/** Corrige o tamanho quando o mapa nasce dentro de um layout que ainda está se ajustando. */
export function AjustarTamanho() {
  const mapa = useMap();
  useEffect(() => {
    const t = window.setTimeout(() => mapa.invalidateSize(), 100);
    return () => window.clearTimeout(t);
  }, [mapa]);
  return null;
}

export function LegendaMapa({ comSupressao = true, comImoveis = false }: { comSupressao?: boolean; comImoveis?: boolean }) {
  return (
    <div className="pointer-events-auto rounded-lg border border-slate-200 bg-white/95 px-3 py-2 font-mono text-[10px] text-slate-600 shadow-sm">
      <ul className="space-y-1">
        {(Object.keys(STATUS) as StatusFazenda[]).map((s) => (
          <li key={s} className="flex items-center gap-2">
            <span
              aria-hidden="true"
              className="inline-block h-0 w-4 border-t-2"
              style={{ borderColor: STATUS[s].cor, borderTopStyle: STATUS[s].traco ? "dashed" : "solid" }}
            />
            {STATUS[s].rotulo.toUpperCase()}
          </li>
        ))}
        <li className="flex items-center gap-2">
          <span aria-hidden="true" className="relative inline-flex size-4 items-center justify-center">
            <span className="absolute inset-0 rounded-full border border-dashed border-slate-500" />
            <span className="size-1.5 rounded-full bg-slate-500" />
          </span>
          PONTO (ATÉ 4 HA)
        </li>
        {comSupressao ? (
          <li className="flex items-center gap-2">
            <span aria-hidden="true" className="inline-block h-3 w-4 rounded-sm border border-[#a63d2f]/60 bg-[repeating-linear-gradient(45deg,rgba(166,61,47,0.55)_0_1.5px,transparent_1.5px_5px)]" />
            SUPRESSÃO PÓS-2020
          </li>
        ) : null}
        {comImoveis ? (
          <li className="flex items-center gap-2">
            <span aria-hidden="true" className="inline-block h-3 w-4 rounded-sm border border-slate-500" />
            IMÓVEL DO CAR
          </li>
        ) : null}
      </ul>
    </div>
  );
}

/** Aviso sobre o estado de uma camada de referência, sobreposto ao mapa. */
export function AvisoCamada({
  estado,
  visivel,
  nome = "supressão do PRODES",
}: {
  estado: EstadoCamada | null;
  visivel: boolean;
  nome?: string;
}) {
  if (!visivel || !estado) return null;
  const texto = estado.erro
    ? `${nome}: indisponível (${estado.erro})`
    : estado.aproximar
      ? `Aproxime o mapa para ver ${nome.startsWith("imóveis") ? "os" : "a"} ${nome}`
      : estado.carregando
        ? `Carregando ${nome}…`
        : estado.truncado
          ? `Mostrando só parte de ${nome}; aproxime para ver tudo`
          : null;
  if (!texto) return null;
  return (
    <p className="pointer-events-auto rounded-full border border-slate-200 bg-white/95 px-3 py-1 font-mono text-[10px] tracking-wide text-slate-600 shadow-sm">
      {texto.toUpperCase()}
    </p>
  );
}

