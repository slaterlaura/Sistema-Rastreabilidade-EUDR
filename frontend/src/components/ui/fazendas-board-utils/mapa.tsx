/**
 * Peças de mapa (Leaflet) do quadro de fazendas.
 *
 * - Camada de supressão do PRODES por baixo, hachurada e desligável (context.md §13).
 * - Busca no mapa (município, estado, código do CAR ou coordenadas) no canto superior esquerdo.
 * - Divisas dos estados sempre visíveis (malha do IBGE, arquivo estático: não gasta execução da API).
 * - Fazenda em polígono: cor do traço = status. Fazenda em ponto: círculo cheio com anel tracejado,
 *   para deixar claro que não há área delimitada.
 */

import { useQuery } from "@tanstack/react-query";
import L from "leaflet";
import { Search, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
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
import { Autocompletar, type Sugestao } from "@/components/ui/autocompletar";
import { CENTRO_PADRAO, limitesDe } from "@/lib/geo";
import { buscarMunicipios, buscarUfs, useLocalidades } from "@/lib/localidades";
import { COR_DESTAQUE, COR_SUPRESSAO, STATUS } from "@/lib/status";
import type {
  CamadaImovel,
  CamadaSupressao as Camada,
  GeometriaFazenda,
  ImovelDetalhe,
  ImovelResumo,
  StatusFazenda,
} from "@/lib/tipos";
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
      <Pane name="calor" style={{ zIndex: 340 }} />
      <Pane name="supressao" style={{ zIndex: 350 }} />
      <Pane name="imoveis" style={{ zIndex: 360 }} />
      <Pane name="divisas" style={{ zIndex: 370 }} />
      <CamadaDivisas />
      <BuscaMapa />
      {children}
    </MapContainer>
  );
}

/** Malha das UFs do IBGE (qualidade mínima, ~100 KB), arquivo estático do site. */
function useDivisas() {
  return useQuery({
    queryKey: ["divisas-ufs"],
    queryFn: async () => {
      const r = await fetch(`${import.meta.env.BASE_URL}ufs-brasil.json`);
      if (!r.ok) throw new Error("Não foi possível carregar as divisas dos estados.");
      return (await r.json()) as GeoJSON.FeatureCollection<GeoJSON.Geometry, { codarea: string }>;
    },
    staleTime: Infinity,
    gcTime: Infinity,
  });
}

/** Divisas dos estados, por cima das camadas e por baixo das fazendas. */
function CamadaDivisas() {
  const { data } = useDivisas();
  if (!data) return null;
  return (
    <GeoJSON
      data={data}
      pane="divisas"
      interactive={false}
      style={() => ({ color: "#334155", weight: 1.1, opacity: 0.75, fill: false })}
    />
  );
}

type Destino =
  | { tipo: "municipio"; nome: string; uf: string; lat: number; lon: number }
  | { tipo: "uf"; sigla: string; nome: string }
  | { tipo: "car"; codigo: string }
  | { tipo: "coordenadas"; lat: number; lon: number };

const PADRAO_CAR = /^[A-Z]{2}-\d{7}-[0-9A-Z.]+$/;

/** "-21.68, -51.07", "-21,68 -51,07" ou "-21.68;-51.07" -> [lat, lon]; inverte se vier lon, lat. */
export function lerCoordenadas(texto: string): [number, number] | null {
  const m = texto.trim().match(/^(-?\d{1,3}(?:[.,]\d+)?)\s*[,;\s]\s*(-?\d{1,3}(?:[.,]\d+)?)$/);
  if (!m) return null;
  let [a, b] = [Number(m[1].replace(",", ".")), Number(m[2].replace(",", "."))];
  if (Math.abs(a) > 34 && Math.abs(b) <= 34) [a, b] = [b, a]; // no Brasil, |lat| ≤ 34 e |lon| ≥ 34 quase sempre
  if (Number.isNaN(a) || Number.isNaN(b) || Math.abs(a) > 90 || Math.abs(b) > 180) return null;
  return [a, b];
}

function rotuloDestino(d: Destino): string {
  if (d.tipo === "municipio") return `${d.nome} · ${d.uf}`;
  if (d.tipo === "uf") return d.nome;
  if (d.tipo === "car") return d.codigo;
  return `${d.lat.toFixed(5)}, ${d.lon.toFixed(5)}`;
}

/**
 * Busca no mapa: leva até um município, um estado, um imóvel do CAR (pelo código) ou um par de coordenadas.
 * Municípios e estados vêm de arquivos estáticos; só o CAR consulta a API.
 */
function BuscaMapa() {
  const mapa = useMap();
  const caixa = useRef<HTMLDivElement>(null);
  const [texto, setTexto] = useState("");
  const [usada, setUsada] = useState(false); // só baixa a lista de municípios quando alguém usa a busca
  const [erro, setErro] = useState<string | null>(null);
  const [destaque, setDestaque] = useState<{ ponto?: [number, number]; geometria?: GeometriaFazenda } | null>(null);
  const { data: locais } = useLocalidades(usada);
  const { data: divisas } = useDivisas();

  // Cliques e rolagem dentro da busca não podem mexer no mapa (nem roubar o foco do campo).
  // O teclado não precisa: o mapa só ouve as setas quando ele mesmo está focado.
  useEffect(() => {
    const el = caixa.current;
    if (!el) return;
    L.DomEvent.disableClickPropagation(el);
    L.DomEvent.disableScrollPropagation(el);
  }, []);

  const sugestoes = useMemo<Sugestao<Destino>[]>(() => {
    const termo = texto.trim();
    if (!termo) return [];
    const lista: Sugestao<Destino>[] = [];
    const coord = lerCoordenadas(termo);
    if (coord) lista.push({ chave: "coord", rotulo: `Ir para ${coord[0]}, ${coord[1]}`, detalhe: "COORDENADAS", valor: { tipo: "coordenadas", lat: coord[0], lon: coord[1] } });
    const codigo = termo.toUpperCase().replace(/\s/g, "");
    if (PADRAO_CAR.test(codigo)) lista.push({ chave: "car", rotulo: codigo, detalhe: "IMÓVEL DO CAR", valor: { tipo: "car", codigo } });
    if (!coord && !PADRAO_CAR.test(codigo)) {
      for (const u of buscarUfs(termo)) lista.push({ chave: `uf-${u.sigla}`, rotulo: u.nome, detalhe: "ESTADO", valor: { tipo: "uf", ...u } });
      for (const m of locais ? buscarMunicipios(locais.municipios, termo, undefined, 7) : []) {
        lista.push({ chave: `m-${m.uf}-${m.nome}`, rotulo: m.nome, detalhe: m.uf, valor: { tipo: "municipio", ...m } });
      }
    }
    return lista;
  }, [texto, locais]);

  async function irPara(d: Destino) {
    setErro(null);
    setTexto(rotuloDestino(d));
    if (d.tipo === "municipio") {
      setDestaque(null);
      mapa.flyTo([d.lat, d.lon], 12, { duration: 0.8 });
    } else if (d.tipo === "coordenadas") {
      setDestaque({ ponto: [d.lat, d.lon] });
      mapa.flyTo([d.lat, d.lon], 15, { duration: 0.8 });
    } else if (d.tipo === "uf") {
      setDestaque(null);
      const codigo = Object.entries(locais?.codigoUf ?? {}).find(([, sigla]) => sigla === d.sigla)?.[0];
      const feicao = divisas?.features.find((f) => f.properties.codarea === codigo);
      if (feicao) mapa.flyToBounds(L.geoJSON(feicao).getBounds(), { padding: [24, 24], duration: 0.8 });
    } else {
      try {
        const imovel = await api.get<ImovelDetalhe>(`/imoveis/${encodeURIComponent(d.codigo)}`);
        setDestaque({ geometria: imovel.geometry });
        mapa.flyToBounds(L.geoJSON(imovel.geometry as GeoJSON.Geometry).getBounds(), { padding: [40, 40], maxZoom: 16, duration: 0.8 });
      } catch (e) {
        setErro((e as Error).message);
      }
    }
  }

  return (
    <>
      <div ref={caixa} className="absolute top-3 left-14 z-[1000] w-[min(20rem,calc(100%-8.5rem))]">
        <div className="relative">
          <Search size={14} aria-hidden="true" className="pointer-events-none absolute top-1/2 left-3 z-10 -translate-y-1/2 text-slate-400" />
          <Autocompletar<Destino>
            valor={texto}
            onValor={(v) => {
              setTexto(v);
              setErro(null);
            }}
            onFocus={() => setUsada(true)}
            sugestoes={sugestoes}
            onEscolher={(d) => void irPara(d)}
            vazio={texto.trim().length >= 2 ? (locais ? "Nada encontrado. Tente o nome do município, a UF, um código do CAR ou coordenadas." : "Carregando municípios…") : undefined}
            placeholder="Município, estado, CAR ou coordenadas"
            aria-label="Buscar no mapa"
            className="h-9 rounded-full border-slate-300 bg-white/95 pr-8 pl-8 text-[13px] shadow-sm"
          />
          {texto ? (
            <button
              type="button"
              onClick={() => {
                setTexto("");
                setErro(null);
                setDestaque(null);
              }}
              className="absolute top-1/2 right-2 z-10 -translate-y-1/2 rounded-full p-1 text-slate-400 hover:text-slate-900"
              title="Limpar busca"
            >
              <X size={13} aria-hidden="true" />
              <span className="sr-only">Limpar busca</span>
            </button>
          ) : null}
        </div>
        {erro ? <p className="mt-1 rounded-md bg-white/95 px-2 py-1 text-xs text-red-700 shadow-sm">{erro}</p> : null}
      </div>
      {destaque?.ponto ? (
        <CircleMarker center={destaque.ponto} radius={7} pathOptions={{ color: "#fff", weight: 2, fillColor: COR_DESTAQUE, fillOpacity: 1 }} interactive={false} />
      ) : null}
      {destaque?.geometria ? (
        <GeoJSON
          key={JSON.stringify(destaque.geometria).length}
          data={destaque.geometria}
          interactive={false}
          style={() => ({ color: COR_DESTAQUE, weight: 2.5, dashArray: "6 4", fill: false })}
        />
      ) : null}
    </>
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

type Limites = [number, number, number, number]; // oeste, sul, leste, norte

/** Recorte visível arredondado numa grade (para reaproveitar cache); com `limites`, cortado nele (ou null se fora). */
function recorteArredondado(mapa: L.Map, passo: number, limites?: Limites): string | null {
  const b = mapa.getBounds();
  let [oeste, sul, leste, norte] = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()];
  if (limites) {
    [oeste, sul] = [Math.max(oeste, limites[0]), Math.max(sul, limites[1])];
    [leste, norte] = [Math.min(leste, limites[2]), Math.min(norte, limites[3])];
    if (oeste >= leste || sul >= norte) return null;
  }
  const baixo = (v: number) => Math.floor(v / passo) * passo;
  const alto = (v: number) => Math.ceil(v / passo) * passo;
  let recorte = [baixo(oeste), baixo(sul), alto(leste), alto(norte)];
  if (limites) {
    // arredondar para fora pode passar do limite: corta de novo (um passo enorme vira "sempre o limite inteiro")
    recorte = [Math.max(recorte[0], limites[0]), Math.max(recorte[1], limites[1]), Math.min(recorte[2], limites[2]), Math.min(recorte[3], limites[3])];
  }
  return recorte.map((v) => v.toFixed(2)).join(",");
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
  /** Acima deste zoom a camada some (ex.: o calor dá lugar aos polígonos). */
  zoomMaximo?: number;
  passo: number;
  /** Só pede dados dentro deste retângulo (ex.: o Brasil). */
  limites?: Limites;
  visivel: boolean;
  versaoDe: (v: VersaoCamada) => number | null;
  onEstado?: (estado: EstadoCamada) => void;
}) {
  const { chave, rota, zoomMinimo, zoomMaximo = Infinity, passo, limites, visivel, versaoDe, onEstado } = opcoes;
  const mapa = useMap();
  const [vista, setVista] = useState(() => ({ zoom: mapa.getZoom(), recorte: recorteArredondado(mapa, passo, limites) }));
  const temporizador = useRef<number>();

  const lerVista = useCallback(() => {
    window.clearTimeout(temporizador.current);
    temporizador.current = window.setTimeout(
      () => setVista({ zoom: mapa.getZoom(), recorte: recorteArredondado(mapa, passo, limites) }),
      350,
    );
    // limites é constante por camada; não entra nas dependências para não recriar o callback
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mapa, passo]);

  useMapEvents({ moveend: lerVista });

  // O mapa costuma ser enquadrado (fitBounds) antes deste componente começar a ouvir eventos;
  // relê a vista depois de montado para não ficar preso ao recorte inicial.
  useEffect(() => {
    lerVista();
    return () => window.clearTimeout(temporizador.current);
  }, [lerVista]);

  const habilitada = visivel && vista.recorte !== null && vista.zoom >= zoomMinimo && vista.zoom <= zoomMaximo;
  const { data: versao } = useVersaoCamada(visivel);
  const v = versao ? (versaoDe(versao) ?? 0) : 0;
  const { data, isFetching, error } = useQuery({
    queryKey: [chave, v, vista.recorte],
    queryFn: () => api.get<T>(`${rota}${rota.includes("?") ? "&" : "?"}bbox=${vista.recorte}&v=${v}`),
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

/**
 * Supressão do PRODES posterior à data de corte.
 * Afastado (zoom até 9): mapa de calor com o desmatamento pré-agregado. Perto (zoom 10+): os polígonos reais,
 * hachurados, por baixo das fazendas.
 */
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
  return (
    <>
      {/* nível 0: células de 0,25° (Brasil/estado); nível 1: 0,05° (região) */}
      {/* passo enorme no nível 0 = sempre o Brasil inteiro: uma única requisição, em cache pela sessão */}
      <CamadaCalor visivel={visivel} nivel={0} zoomMinimo={0} zoomMaximo={6} passo={100} />
      <CamadaCalor visivel={visivel} nivel={1} zoomMinimo={7} zoomMaximo={9} passo={1} />
      {data ? (
        <GeoJSON
          key={`${chaveRender}-${data.features.length}`}
          data={data as GeoJSON.FeatureCollection}
          pane="supressao"
          interactive={false}
          style={() => ({ color: COR_SUPRESSAO, weight: 0.8, opacity: 0.7, className: "supressao-hachura" })}
        />
      ) : null}
    </>
  );
}

interface RespostaCalor {
  nivel: number;
  truncado: boolean;
  max: number;
  pontos: [number, number, number][];
}

const BRASIL: Limites = [-75, -35, -28, 7];

/** Faixas de cor sólidas (sem degradê), relativas ao percentil 95 dos hectares no recorte. */
export const CLASSES_CALOR = [
  { ate: 0.08, cor: "#fde68a" },
  { ate: 0.25, cor: "#fbbf24" },
  { ate: 0.5, cor: "#f97316" },
  { ate: 1, cor: "#dc2626" },
  { ate: Infinity, cor: "#7f1d1d" },
];

interface Celula {
  sul: number;
  oeste: number;
  norte: number;
  leste: number;
  cor: string;
}

/** Desenha as células da agregação como quadrados cheios, em blocos (tiles) de canvas. */
class GradeCalor extends L.GridLayer {
  constructor(
    private mapa: L.Map,
    private celulas: Celula[],
    opcoes: L.GridLayerOptions,
  ) {
    super(opcoes);
  }

  createTile(coords: L.Coords): HTMLElement {
    const bloco = document.createElement("canvas");
    const tamanho = this.getTileSize();
    bloco.width = tamanho.x;
    bloco.height = tamanho.y;
    const ctx = bloco.getContext("2d");
    if (!ctx) return bloco;
    const origem = coords.scaleBy(tamanho);
    const noroeste = this.mapa.unproject(origem, coords.z);
    const sudeste = this.mapa.unproject(origem.add(tamanho), coords.z);
    for (const c of this.celulas) {
      if (c.norte < sudeste.lat || c.sul > noroeste.lat || c.leste < noroeste.lng || c.oeste > sudeste.lng) continue;
      const a = this.mapa.project([c.norte, c.oeste], coords.z).subtract(origem);
      const b = this.mapa.project([c.sul, c.leste], coords.z).subtract(origem);
      // arredonda para fora: células vizinhas encostam, sem frestas entre elas
      const x = Math.floor(a.x);
      const y = Math.floor(a.y);
      ctx.fillStyle = c.cor;
      ctx.fillRect(x, y, Math.max(1, Math.ceil(b.x) - x), Math.max(1, Math.ceil(b.y) - y));
    }
    return bloco;
  }
}

/** Mapa de calor de um nível de agregação (células sólidas), só dentro da sua faixa de zoom. */
function CamadaCalor({
  visivel,
  nivel,
  zoomMinimo,
  zoomMaximo,
  passo,
}: {
  visivel: boolean;
  nivel: 0 | 1;
  zoomMinimo: number;
  zoomMaximo: number;
  passo: number;
}) {
  const mapa = useMap();
  const { data } = useCamadaRecortada<RespostaCalor>({
    chave: `camada-calor-${nivel}`,
    rota: `/camada/prodes/calor?nivel=${nivel}`,
    zoomMinimo,
    zoomMaximo,
    passo,
    limites: BRASIL,
    visivel,
    versaoDe: (v) => v.versao,
  });

  useEffect(() => {
    if (!data || data.pontos.length === 0) return;
    // Cada ponto é o centro ponderado da sua célula: a célula é a casa da grade que o contém.
    const grau = nivel === 0 ? 0.25 : 0.05;
    const max = Math.max(data.max, 1);
    const celulas: Celula[] = data.pontos.map(([lat, lon, ha]) => {
      const sul = Math.floor(lat / grau) * grau;
      const oeste = Math.floor(lon / grau) * grau;
      const razao = ha / max;
      const cor = (CLASSES_CALOR.find((c) => razao <= c.ate) ?? CLASSES_CALOR[CLASSES_CALOR.length - 1]).cor;
      return { sul, oeste, norte: sul + grau, leste: oeste + grau, cor };
    });
    const camada = new GradeCalor(mapa, celulas, { pane: "calor", opacity: 0.78, minZoom: zoomMinimo, maxZoom: zoomMaximo }).addTo(mapa);
    return () => {
      camada.remove();
    };
  }, [mapa, data, nivel, zoomMinimo, zoomMaximo]);

  return null;
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
            SUPRESSÃO PÓS-2020 (ZOOM 10+)
          </li>
        ) : null}
        {comSupressao ? (
          <li className="flex items-center gap-2">
            <span aria-hidden="true" className="inline-flex">
              {CLASSES_CALOR.map((c) => (
                <span key={c.cor} className="inline-block size-2.5" style={{ backgroundColor: c.cor }} />
              ))}
            </span>
            DESMATAMENTO: MENOS → MAIS (AFASTADO)
          </li>
        ) : null}
        <li className="flex items-center gap-2">
          <span aria-hidden="true" className="inline-block h-0 w-4 border-t border-slate-700" />
          DIVISA DE ESTADO
        </li>
        {comImoveis ? (
          <li className="flex items-center gap-2">
            <span aria-hidden="true" className="inline-block h-3 w-4 rounded-sm border border-slate-500" />
            IMÓVEL DO CAR (REFERÊNCIA, NÃO CADASTRADO)
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
  nome = "polígonos do PRODES",
}: {
  estado: EstadoCamada | null;
  visivel: boolean;
  nome?: string;
}) {
  if (!visivel || !estado) return null;
  const texto = estado.erro
    ? `${nome}: indisponível (${estado.erro})`
    : estado.aproximar
      ? `Aproxime o mapa para ver ${/^(imóveis|polígonos)/.test(nome) ? "os" : "a"} ${nome}`
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

