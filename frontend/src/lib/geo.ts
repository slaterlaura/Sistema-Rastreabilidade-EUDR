import type { Position } from "geojson";
import L from "leaflet";
import type { GeometriaFazenda } from "@/lib/tipos";

const RAIO_TERRA = 6378137;

/** Área geodésica aproximada de um anel [lng, lat], em hectares (só para orientar no desenho). */
export function areaAnelHa(anel: Position[]): number {
  if (anel.length < 3) return 0;
  let soma = 0;
  for (let i = 0; i < anel.length; i++) {
    const [lng1, lat1] = anel[i];
    const [lng2, lat2] = anel[(i + 1) % anel.length];
    soma +=
      ((lng2 - lng1) * Math.PI) / 180 *
      (2 + Math.sin((lat1 * Math.PI) / 180) + Math.sin((lat2 * Math.PI) / 180));
  }
  return Math.abs((soma * RAIO_TERRA * RAIO_TERRA) / 2) / 10_000;
}

export function limitesDe(geometrias: GeometriaFazenda[]): L.LatLngBounds | null {
  if (geometrias.length === 0) return null;
  const limites = L.geoJSON({
    type: "FeatureCollection",
    features: geometrias.map((g) => ({ type: "Feature", geometry: g, properties: {} })),
  } as GeoJSON.FeatureCollection).getBounds();
  return limites.isValid() ? limites : null;
}

/** Centro do Brasil, para quando ainda não há fazendas. */
export const CENTRO_PADRAO: [number, number] = [-15.8, -47.9];
