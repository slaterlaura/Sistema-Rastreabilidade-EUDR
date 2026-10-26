import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Documento, Dossie, Embarque, Fazenda, Fornecedor } from "@/lib/tipos";

export const chaves = {
  fornecedores: ["fornecedores"] as const,
  fazendas: ["fazendas"] as const,
  embarques: ["embarques"] as const,
  dossies: ["dossies"] as const,
  documentos: (dono: "fornecedores" | "fazendas", id: number) => ["documentos", dono, id] as const,
};

export const useFornecedores = () =>
  useQuery({ queryKey: chaves.fornecedores, queryFn: () => api.get<Fornecedor[]>("/fornecedores") });

export const useFazendas = () =>
  useQuery({ queryKey: chaves.fazendas, queryFn: () => api.get<Fazenda[]>("/fazendas") });

export const useEmbarques = () =>
  useQuery({ queryKey: chaves.embarques, queryFn: () => api.get<Embarque[]>("/embarques") });

export const useEmbarque = (id: number) =>
  useQuery({ queryKey: [...chaves.embarques, id], queryFn: () => api.get<Embarque>(`/embarques/${id}`) });

export const useDossies = () =>
  useQuery({ queryKey: chaves.dossies, queryFn: () => api.get<Dossie[]>("/dossies") });

export const useDossie = (id: number) =>
  useQuery({
    queryKey: [...chaves.dossies, id],
    queryFn: () => api.get<Dossie>(`/dossies/${id}`),
    staleTime: Infinity, // dossiê é imutável (R3)
  });

export const useDocumentos = (dono: "fornecedores" | "fazendas", id: number) =>
  useQuery({
    queryKey: chaves.documentos(dono, id),
    queryFn: () => api.get<Documento[]>(`/${dono}/${id}/documentos`),
  });

/** Depois de mudar fazendas, fornecedores e embarques mostram contagens e status derivados delas. */
export function useInvalidarCadastro() {
  const queryClient = useQueryClient();
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: chaves.fazendas }),
      queryClient.invalidateQueries({ queryKey: chaves.fornecedores }),
      queryClient.invalidateQueries({ queryKey: chaves.embarques }),
    ]);
}

export function useReverificarTodas() {
  const invalidar = useInvalidarCadastro();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      api.post<{ verificadas: number; mudaram_de_status: { nome: string; de: string; para: string }[] }>(
        "/fazendas/reverificar",
      ),
    // reprocessar costuma vir depois de uma carga nova: o mapa também relê a camada
    onSuccess: () => Promise.all([invalidar(), queryClient.invalidateQueries({ queryKey: ["camada-versao"] })]),
  });
}
