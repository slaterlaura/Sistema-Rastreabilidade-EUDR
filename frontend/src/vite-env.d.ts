/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** URL da API (Function no Azure ou uvicorn local), sem barra no final. */
  readonly VITE_API_URL?: string;
}
