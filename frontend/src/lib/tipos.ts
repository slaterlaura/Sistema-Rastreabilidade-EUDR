import type { Geometry, Point, Polygon, MultiPolygon } from "geojson";

export type StatusFazenda = "pendente" | "apta" | "bloqueada";
export type GeometriaFazenda = Polygon | MultiPolygon | Point;

export interface Usuario {
  id: number;
  nome: string;
  email: string;
}

export interface Fornecedor {
  id: number;
  nome: string;
  documento: string;
  tipo_pessoa: "PF" | "PJ";
  email: string | null;
  telefone: string | null;
  municipio: string | null;
  uf: string | null;
  ativo: boolean;
  criado_em: string;
  atualizado_em: string;
  total_fazendas: number;
}

export interface Fazenda {
  id: number;
  fornecedor_id: number;
  nome: string;
  car_codigo: string | null;
  ccir: string | null;
  nirf: string | null;
  matricula: string | null;
  municipio: string | null;
  uf: string | null;
  area_declarada_ha: string | null;
  status: StatusFazenda;
  area_sobreposta_m2: string;
  verificada_em: string | null;
  camada_versao_id: number | null;
  criado_em: string;
  atualizado_em: string;
  geometry: GeometriaFazenda;
}

export type TipoDocumento = "car" | "ccir" | "matricula" | "licenca" | "contrato" | "outro";

export interface Documento {
  id: number;
  fornecedor_id: number | null;
  fazenda_id: number | null;
  tipo: TipoDocumento;
  nome_arquivo: string;
  content_type: string;
  tamanho_bytes: number;
  sha256: string;
  validade: string | null;
  criado_em: string;
}

export interface Parcela {
  id: number;
  fazenda_id: number;
  fazenda_nome: string;
  fazenda_status: StatusFazenda;
  quantidade_kg: string;
  observacao: string | null;
}

export interface Embarque {
  id: number;
  identificacao: string;
  data_embarque: string;
  destino: string;
  status: "rascunho" | "fechado";
  fechado_em: string | null;
  criado_em: string;
  parcelas: Parcela[];
  total_kg: string;
  dossie_id: number | null;
}

export interface DocumentoRetrato {
  id: number;
  tipo: TipoDocumento;
  nome_arquivo: string;
  sha256: string;
  validade: string | null;
}

export interface ParcelaRetrato {
  parcela_id: number;
  quantidade_kg: number;
  observacao: string | null;
  fazenda: {
    id: number;
    nome: string;
    car_codigo: string | null;
    ccir: string | null;
    nirf: string | null;
    matricula: string | null;
    municipio: string | null;
    uf: string | null;
    area_declarada_ha: number | null;
    status: StatusFazenda;
    area_sobreposta_m2: number;
    verificada_em: string | null;
    camada_versao_id: number | null;
    geometry: GeometriaFazenda;
    documentos: DocumentoRetrato[];
  };
  fornecedor: {
    id: number;
    nome: string;
    documento: string;
    tipo_pessoa: string;
    documentos: DocumentoRetrato[];
  };
}

export interface Retrato {
  versao_retrato: number;
  gerado_em: string;
  exportador: { nome: string; email: string };
  embarque: { id: number; identificacao: string; data_embarque: string; destino: string };
  criterios: { data_corte_desmatamento: string; tolerancia_m2: number; observacao: string };
  camadas_referencia: {
    id: number;
    origem: string;
    bioma: string;
    uf: string | null;
    arquivo: string | null;
    n_feicoes: number;
    carregada_em: string;
  }[];
  total_kg: number;
  parcelas: ParcelaRetrato[];
}

export interface Dossie {
  id: number;
  embarque_id: number;
  embarque_identificacao: string;
  destino: string;
  data_embarque: string;
  n_parcelas: number;
  total_kg: string;
  gerado_em: string;
  retrato: Retrato | null;
}

export interface CamadaSupressao {
  type: "FeatureCollection";
  truncado: boolean;
  features: {
    type: "Feature";
    geometry: Geometry;
    properties: { id: number; ano: number; area_km: number | null };
  }[];
}
