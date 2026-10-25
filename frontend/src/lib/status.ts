import type { StatusFazenda } from "@/lib/tipos";

/** Status codificado em cor do traço (context.md §13). Nunca só em texto. */
export const STATUS: Record<StatusFazenda, { rotulo: string; cor: string; traco: string | undefined }> = {
  apta: { rotulo: "Apta", cor: "#48864f", traco: undefined },
  bloqueada: { rotulo: "Bloqueada", cor: "#a63d2f", traco: undefined },
  pendente: { rotulo: "Pendente", cor: "#8a8f86", traco: "6 5" },
};

export const COR_DESTAQUE = "#c65d24";
export const COR_SUPRESSAO = "#a63d2f";
