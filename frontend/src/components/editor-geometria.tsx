/**
 * Desenho de fazenda no mapa, pensado para quem não conhece SIG: clicar adiciona um vértice,
 * "Desfazer" remove o último, a área aparece em hectares enquanto se desenha.
 * Ponto só para áreas de até 4 ha (R4); o servidor também valida.
 */

import type { Position } from "geojson";
import { Hexagon, MapPin, Trash2, Undo2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { CircleMarker, Polygon, Polyline, useMap, useMapEvents } from "react-leaflet";
import { areaAnelHa } from "@/lib/geo";
import { ha } from "@/lib/formato";
import { COR_DESTAQUE } from "@/lib/status";
import type { GeometriaFazenda } from "@/lib/tipos";
import { cn } from "@/lib/utils";

export type ModoDesenho = "poligono" | "ponto";
type LatLng = [number, number];

export interface EstadoDesenho {
  modo: ModoDesenho;
  vertices: LatLng[];
  ponto: LatLng | null;
  multiParte: boolean;
  setModo: (m: ModoDesenho) => void;
  adicionar: (p: LatLng) => void;
  desfazer: () => void;
  limpar: () => void;
  reiniciar: (g?: GeometriaFazenda | null) => void;
  geometria: GeometriaFazenda | null;
  areaHa: number;
}

interface EstadoBase {
  modo: ModoDesenho;
  vertices: LatLng[];
  ponto: LatLng | null;
  multiParte: boolean;
}

function inicializar(g?: GeometriaFazenda | null): EstadoBase {
  if (!g) return { modo: "poligono", vertices: [], ponto: null, multiParte: false };
  if (g.type === "Point") {
    return { modo: "ponto", vertices: [], ponto: [g.coordinates[1], g.coordinates[0]], multiParte: false };
  }
  const aneis: Position[][] = g.type === "Polygon" ? [g.coordinates[0]] : g.coordinates.map((p) => p[0]);
  if (aneis.length !== 1) return { modo: "poligono", vertices: [], ponto: null, multiParte: true };
  const anel = aneis[0].slice(0, -1); // GeoJSON repete o primeiro vértice no fim
  return { modo: "poligono", vertices: anel.map(([lng, lat]) => [lat, lng] as LatLng), ponto: null, multiParte: false };
}

export function useDesenho(inicial?: GeometriaFazenda | null): EstadoDesenho {
  const [estado, setEstado] = useState<EstadoBase>(() => inicializar(inicial));

  const geometria = useMemo<GeometriaFazenda | null>(() => {
    if (estado.modo === "ponto") {
      return estado.ponto ? { type: "Point", coordinates: [estado.ponto[1], estado.ponto[0]] } : null;
    }
    if (estado.vertices.length < 3) return null;
    const anel = estado.vertices.map(([lat, lng]) => [lng, lat]);
    return { type: "Polygon", coordinates: [[...anel, anel[0]]] };
  }, [estado]);

  const areaHa = useMemo(
    () => (estado.modo === "poligono" ? areaAnelHa(estado.vertices.map(([lat, lng]) => [lng, lat])) : 0),
    [estado],
  );

  return {
    ...estado,
    geometria,
    areaHa,
    setModo: (modo) => setEstado((e) => ({ ...e, modo })),
    adicionar: (p) =>
      setEstado((e) => (e.modo === "ponto" ? { ...e, ponto: p } : { ...e, vertices: [...e.vertices, p], multiParte: false })),
    desfazer: () =>
      setEstado((e) => (e.modo === "ponto" ? { ...e, ponto: null } : { ...e, vertices: e.vertices.slice(0, -1) })),
    limpar: () => setEstado((e) => ({ ...e, vertices: [], ponto: null, multiParte: false })),
    reiniciar: (g) => setEstado(inicializar(g)),
  };
}

/** Vai dentro do <Mapa>: captura cliques e desenha o rascunho em laranja. */
export function CamadaDesenho({ desenho, ativo = true }: { desenho: EstadoDesenho; ativo?: boolean }) {
  const mapa = useMap();
  useEffect(() => {
    const el = mapa.getContainer();
    el.style.cursor = ativo ? "crosshair" : "";
    if (ativo) mapa.doubleClickZoom.disable();
    else mapa.doubleClickZoom.enable();
    return () => {
      el.style.cursor = "";
      mapa.doubleClickZoom.enable();
    };
  }, [mapa, ativo]);

  useMapEvents({
    click: (e) => {
      if (ativo) desenho.adicionar([e.latlng.lat, e.latlng.lng]);
    },
  });

  const estilo = { color: COR_DESTAQUE, weight: 2.5, dashArray: "6 4" };
  if (desenho.modo === "ponto") {
    if (!desenho.ponto) return null;
    return (
      <>
        <CircleMarker center={desenho.ponto} radius={12} pathOptions={{ ...estilo, weight: 1.5, dashArray: "3 4", fill: false }} interactive={false} />
        <CircleMarker center={desenho.ponto} radius={5} pathOptions={{ color: "#fff", weight: 1.5, fillColor: COR_DESTAQUE, fillOpacity: 1 }} interactive={false} />
      </>
    );
  }
  return (
    <>
      {desenho.vertices.length >= 3 ? (
        <Polygon positions={desenho.vertices} pathOptions={{ ...estilo, fillColor: COR_DESTAQUE, fillOpacity: 0.12 }} interactive={false} />
      ) : desenho.vertices.length === 2 ? (
        <Polyline positions={desenho.vertices} pathOptions={estilo} interactive={false} />
      ) : null}
      {desenho.vertices.map((v, i) => (
        <CircleMarker
          key={`${i}-${v[0]}-${v[1]}`}
          center={v}
          radius={i === desenho.vertices.length - 1 ? 5 : 3.5}
          pathOptions={{ color: COR_DESTAQUE, weight: 1.5, fillColor: "#fff", fillOpacity: 1 }}
          interactive={false}
        />
      ))}
    </>
  );
}

/** Controles do desenho (fora do mapa, junto do formulário). */
export function ControlesDesenho({ desenho, areaDeclaradaHa }: { desenho: EstadoDesenho; areaDeclaradaHa?: number | null }) {
  const pontoGrande = desenho.modo === "ponto" && (areaDeclaradaHa ?? 0) > 4;
  return (
    <div className="space-y-3">
      <div role="group" aria-label="Forma da fazenda" className="flex gap-1.5">
        {(
          [
            { modo: "poligono", rotulo: "Polígono", icone: Hexagon },
            { modo: "ponto", rotulo: "Ponto (até 4 ha)", icone: MapPin },
          ] as const
        ).map(({ modo, rotulo, icone: Icone }) => (
          <button
            key={modo}
            type="button"
            onClick={() => desenho.setModo(modo)}
            aria-pressed={desenho.modo === modo}
            className={cn(
              "flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium",
              desenho.modo === modo ? "border-slate-950 bg-slate-950 text-white" : "border-slate-200 text-slate-600 hover:text-slate-950",
            )}
          >
            <Icone size={12} aria-hidden="true" /> {rotulo}
          </button>
        ))}
      </div>

      <p className="text-xs leading-relaxed text-slate-600">
        {desenho.modo === "poligono"
          ? "Clique no mapa contornando a área, um vértice por clique. Com três ou mais vértices o contorno fecha sozinho. Use a camada Satélite (canto do mapa) para enxergar a lavoura."
          : "Clique no centro da área. Ponto só é aceito para fazendas de até 4 ha; acima disso, desenhe o polígono."}
      </p>

      {desenho.multiParte ? (
        <p className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-900">
          A geometria atual tem várias partes (veio de importação). Para alterá-la, limpe e desenhe de novo.
        </p>
      ) : null}

      <div className="flex items-center justify-between gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
        <span className="font-mono text-[11px] text-slate-600">
          {desenho.modo === "poligono"
            ? `${desenho.vertices.length} VÉRTICES · ${desenho.vertices.length >= 3 ? `≈ ${ha(desenho.areaHa)}` : "contorno aberto"}`
            : desenho.ponto
              ? `PONTO ${desenho.ponto[0].toFixed(5)}, ${desenho.ponto[1].toFixed(5)}`
              : "NENHUM PONTO"}
        </span>
        <span className="flex gap-1">
          <button type="button" onClick={desenho.desfazer} className="rounded-md p-1.5 text-slate-500 hover:bg-white hover:text-slate-950" title="Desfazer último">
            <Undo2 size={14} aria-hidden="true" />
            <span className="sr-only">Desfazer último</span>
          </button>
          <button type="button" onClick={desenho.limpar} className="rounded-md p-1.5 text-slate-500 hover:bg-white hover:text-slate-950" title="Limpar">
            <Trash2 size={14} aria-hidden="true" />
            <span className="sr-only">Limpar desenho</span>
          </button>
        </span>
      </div>
      {desenho.modo === "poligono" && desenho.areaHa > 100_000 ? (
        <p className="text-xs text-[#a63d2f]">
          Contorno com mais de 100.000 ha: o servidor vai recusar. Aproxime o mapa e desenhe só a área da fazenda.
        </p>
      ) : null}
      {pontoGrande ? (
        <p className="text-xs text-[#a63d2f]">A área declarada passa de 4 ha: o servidor vai recusar o ponto.</p>
      ) : null}
    </div>
  );
}
