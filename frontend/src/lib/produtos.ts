/**
 * Produto e especificação de qualidade do embarque (café, EUDR anexo I: posição SH 0901).
 * A lista de produtos espelha backend/app/produtos.py: ao mudar lá, mude aqui.
 * As demais listas são sugestões da classificação comercial (COB); o servidor aceita texto livre.
 */

import type { Produto } from "@/lib/tipos";

export const PRODUTOS: { codigo: string; descricao: string; codigo_sh: string }[] = [
  { codigo: "cafe_arabica_verde", descricao: "Café arábica verde (cru, em grão)", codigo_sh: "0901.11" },
  { codigo: "cafe_conilon_verde", descricao: "Café conilon/robusta verde (cru, em grão)", codigo_sh: "0901.11" },
  { codigo: "cafe_blend_verde", descricao: "Café verde, blend arábica e conilon", codigo_sh: "0901.11" },
  { codigo: "cafe_verde_descafeinado", descricao: "Café verde descafeinado", codigo_sh: "0901.12" },
  { codigo: "cafe_torrado_grao", descricao: "Café torrado em grão", codigo_sh: "0901.21" },
];

/** Tipo pela Classificação Oficial Brasileira, na nomenclatura de Nova York (defeitos por amostra). */
export const TIPOS = ["NY 2", "NY 2/3", "NY 3", "NY 3/4", "NY 4", "NY 4/5", "NY 5", "NY 6", "NY 7"];

/** Bebida (prova de xícara). Arábica e conilon têm escalas diferentes. */
export const BEBIDAS: { grupo: string; opcoes: string[] }[] = [
  { grupo: "Arábica", opcoes: ["Estritamente mole", "Mole", "Apenas mole", "Dura", "Riada", "Rio", "Rio zona"] },
  { grupo: "Conilon/robusta", opcoes: ["Excelente", "Boa", "Regular", "Anormal"] },
];

/** Peneira: tamanho do grão em 64 avos de polegada. */
export const PENEIRAS = ["19", "18", "17/18", "16/17", "16", "15/16", "14/16", "13/14", "Moca 10/12", "Moca 9/11"];

/** Regiões produtoras (sugestões; aceita qualquer texto). */
export const REGIOES = [
  "Cerrado Mineiro",
  "Sul de Minas",
  "Matas de Minas",
  "Chapada de Minas",
  "Mogiana",
  "Alta Mogiana",
  "Alta Paulista (SP)",
  "Norte Pioneiro do Paraná",
  "Montanhas do Espírito Santo",
  "Conilon Capixaba (ES)",
  "Caparaó",
  "Oeste da Bahia",
  "Chapada Diamantina (BA)",
  "Planalto da Bahia",
  "Matas de Rondônia",
];

/** "Café arábica verde (cru, em grão) · SH 0901.11" */
export function textoProduto(p: Produto | null | undefined): string {
  return p ? `${p.descricao}${p.codigo_sh ? ` · SH ${p.codigo_sh}` : ""}` : "Produto não informado";
}

/** "NY 2/3 · bebida dura · peneira 17/18 · Cerrado Mineiro" (vazio se nada foi informado). */
export function textoEspecificacao(e: {
  tipo_classificacao?: string | null;
  bebida?: string | null;
  peneira?: string | null;
  regiao_origem?: string | null;
}): string {
  return [
    e.tipo_classificacao,
    e.bebida && `bebida ${e.bebida.toLowerCase()}`,
    e.peneira && `peneira ${e.peneira}`,
    e.regiao_origem,
  ]
    .filter(Boolean)
    .join(" · ");
}
