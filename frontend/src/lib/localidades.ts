/**
 * Estados e municípios do IBGE para sugestões de formulário e para a busca no mapa.
 * A lista de municípios é um arquivo estático do site (public/municipios.json, ~80 KB comprimido),
 * baixado uma vez quando precisa: não gasta execução da API.
 */

import { useQuery } from "@tanstack/react-query";

export const UFS: { sigla: string; nome: string }[] = [
  { sigla: "AC", nome: "Acre" },
  { sigla: "AL", nome: "Alagoas" },
  { sigla: "AP", nome: "Amapá" },
  { sigla: "AM", nome: "Amazonas" },
  { sigla: "BA", nome: "Bahia" },
  { sigla: "CE", nome: "Ceará" },
  { sigla: "DF", nome: "Distrito Federal" },
  { sigla: "ES", nome: "Espírito Santo" },
  { sigla: "GO", nome: "Goiás" },
  { sigla: "MA", nome: "Maranhão" },
  { sigla: "MT", nome: "Mato Grosso" },
  { sigla: "MS", nome: "Mato Grosso do Sul" },
  { sigla: "MG", nome: "Minas Gerais" },
  { sigla: "PA", nome: "Pará" },
  { sigla: "PB", nome: "Paraíba" },
  { sigla: "PR", nome: "Paraná" },
  { sigla: "PE", nome: "Pernambuco" },
  { sigla: "PI", nome: "Piauí" },
  { sigla: "RJ", nome: "Rio de Janeiro" },
  { sigla: "RN", nome: "Rio Grande do Norte" },
  { sigla: "RS", nome: "Rio Grande do Sul" },
  { sigla: "RO", nome: "Rondônia" },
  { sigla: "RR", nome: "Roraima" },
  { sigla: "SC", nome: "Santa Catarina" },
  { sigla: "SP", nome: "São Paulo" },
  { sigla: "SE", nome: "Sergipe" },
  { sigla: "TO", nome: "Tocantins" },
];

export interface Municipio {
  nome: string;
  uf: string;
  lat: number;
  lon: number;
  chave: string; // nome sem acento e em minúsculas, para comparar
}

interface ArquivoMunicipios {
  ufs: [number, string, string][]; // código IBGE, sigla, nome
  municipios: [string, string, number, number][]; // nome, sigla, lat, lon
}

export interface Localidades {
  municipios: Municipio[];
  codigoUf: Record<string, string>; // código IBGE da UF -> sigla
}

/** "São José do Rio Preto" -> "sao jose do rio preto". */
export function normalizar(texto: string): string {
  return texto
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .trim();
}

export function useLocalidades(habilitada = true) {
  return useQuery({
    queryKey: ["localidades"],
    queryFn: async (): Promise<Localidades> => {
      const r = await fetch(`${import.meta.env.BASE_URL}municipios.json`);
      if (!r.ok) throw new Error("Não foi possível carregar a lista de municípios.");
      const dados = (await r.json()) as ArquivoMunicipios;
      return {
        municipios: dados.municipios.map(([nome, uf, lat, lon]) => ({ nome, uf, lat, lon, chave: normalizar(nome) })),
        codigoUf: Object.fromEntries(dados.ufs.map(([codigo, sigla]) => [String(codigo), sigla])),
      };
    },
    enabled: habilitada,
    staleTime: Infinity,
    gcTime: Infinity,
  });
}

/** Municípios que começam com o termo primeiro, depois os que o contêm; opcionalmente só de uma UF. */
export function buscarMunicipios(lista: Municipio[], termo: string, uf?: string, limite = 8): Municipio[] {
  const t = normalizar(termo);
  if (t.length < 2) return [];
  const daUf = uf ? lista.filter((m) => m.uf === uf.toUpperCase()) : lista;
  const comeca = daUf.filter((m) => m.chave.startsWith(t));
  const contem = daUf.filter((m) => !m.chave.startsWith(t) && m.chave.includes(t));
  return [...comeca, ...contem].slice(0, limite);
}

export function buscarUfs(termo: string): typeof UFS {
  const t = normalizar(termo);
  if (!t) return [];
  return UFS.filter((u) => u.sigla.toLowerCase() === t || normalizar(u.nome).startsWith(t));
}
