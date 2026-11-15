import "leaflet";

declare module "leaflet" {
  /** [latitude, longitude, intensidade de 0 a 1] */
  type PontoCalor = [number, number, number];

  interface HeatLayerOptions {
    minOpacity?: number;
    maxZoom?: number;
    max?: number;
    radius?: number;
    blur?: number;
    gradient?: Record<number, string>;
  }

  interface HeatLayer extends Layer {
    setLatLngs(pontos: PontoCalor[]): this;
    setOptions(opcoes: HeatLayerOptions): this;
    redraw(): this;
  }

  function heatLayer(pontos: PontoCalor[], opcoes?: HeatLayerOptions): HeatLayer;
}

declare module "leaflet.heat";
