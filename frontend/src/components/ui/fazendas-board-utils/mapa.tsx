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
import type { CamadaSupressao as Camada, GeometriaFazenda, StatusFazenda } from "@/lib/tipos";
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

const ZOOM_MINIMO_CAMADA = 10;
const PASSO_GRADE = 0.25; // arredonda o recorte para reaproveitar respostas em cache

function recorteArredondado(mapa: L.Map): string {
  const b = mapa.getBounds();
  const baixo = (v: number) => Math.floor(v / PASSO_GRADE) * PASSO_GRADE;
  const alto = (v: number) => Math.ceil(v / PASSO_GRADE) * PASSO_GRADE;
  return [baixo(b.getWest()), baixo(b.getSouth()), alto(b.getEast()), alto(b.getNorth())]
    .map((v) => v.toFixed(2))
    .join(",");
}

/**
 * Busca a supressão pós-2020 só do recorte visível e só com zoom suficiente.
 * Cada busca é uma execução da Function: recortes iguais vêm do cache, e o mapa
 * não consulta nada enquanto está afastado.
 */
export function CamadaSupressao({
  visivel,
  onEstado,
}: {
  visivel: boolean;
  onEstado?: (estado: EstadoCamada) => void;
}) {
  const mapa = useMap();
  const [vista, setVista] = useState(() => ({ zoom: mapa.getZoom(), recorte: recorteArredondado(mapa) }));
  const temporizador = useRef<number>();

  const lerVista = useCallback(() => {
    window.clearTimeout(temporizador.current);
    temporizador.current = window.setTimeout(
      () => setVista({ zoom: mapa.getZoom(), recorte: recorteArredondado(mapa) }),
      350,
    );
  }, [mapa]);

  useMapEvents({ moveend: lerVista });

  // O mapa costuma ser enquadrado (fitBounds) antes deste componente começar a ouvir eventos;
  // relê a vista depois de montado para não ficar preso ao recorte inicial.
  useEffect(() => {
    lerVista();
    return () => window.clearTimeout(temporizador.current);
  }, [lerVista]);

  const habilitada = visivel && vista.zoom >= ZOOM_MINIMO_CAMADA;
  // A versão vai na URL: depois de uma carga nova do PRODES, o navegador não reaproveita a camada velha.
  const { data: versao } = useVersaoCamada(visivel);
  const v = versao?.versao ?? 0;
  const { data, isFetching, error } = useQuery({
    queryKey: ["camada-prodes", v, vista.recorte],
    queryFn: () => api.get<Camada>(`/camada/prodes?bbox=${vista.recorte}&v=${v}`),
    enabled: habilitada && versao !== undefined,
    staleTime: Infinity,
    gcTime: 30 * 60 * 1000,
    placeholderData: (anterior) => anterior,
  });

  useEffect(() => {
    onEstado?.({
      carregando: habilitada && isFetching,
      aproximar: visivel && vista.zoom < ZOOM_MINIMO_CAMADA,
      truncado: Boolean(habilitada && data?.truncado),
      erro: error ? (error as Error).message : null,
    });
  }, [onEstado, habilitada, isFetching, visivel, vista.zoom, data?.truncado, error]);

  if (!habilitada || !data) return null;
  return (
    <GeoJSON
      key={`${v}-${vista.recorte}-${data.features.length}`}
      data={data as GeoJSON.FeatureCollection}
      pane="supressao"
      interactive={false}
      style={() => ({
        color: COR_SUPRESSAO,
        weight: 0.8,
        opacity: 0.7,
        className: "supressao-hachura",
      })}
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

export function LegendaMapa({ comSupressao = true }: { comSupressao?: boolean }) {
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
      </ul>
    </div>
  );
}

/** Aviso sobre o estado da camada de supressão, sobreposto ao mapa. */
export function AvisoCamada({ estado, visivel }: { estado: EstadoCamada | null; visivel: boolean }) {
  if (!visivel || !estado) return null;
  const texto = estado.erro
    ? `Camada de supressão indisponível: ${estado.erro}`
    : estado.aproximar
      ? "Aproxime o mapa para ver a supressão do PRODES"
      : estado.carregando
        ? "Carregando supressão…"
        : estado.truncado
          ? "Mostrando só os maiores polígonos de supressão; aproxime para ver todos"
          : null;
  if (!texto) return null;
  return (
    <p className="pointer-events-auto rounded-full border border-slate-200 bg-white/95 px-3 py-1 font-mono text-[10px] tracking-wide text-slate-600 shadow-sm">
      {texto.toUpperCase()}
    </p>
  );
}

