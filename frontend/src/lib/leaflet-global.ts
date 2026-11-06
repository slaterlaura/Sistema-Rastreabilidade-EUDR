import L from "leaflet";

// O leaflet.heat (0.2.0) procura o Leaflet no objeto global `window.L`, que o import ESM não cria.
// Este módulo precisa ser importado ANTES de "leaflet.heat".
(window as unknown as { L: typeof L }).L = L;

export default L;
