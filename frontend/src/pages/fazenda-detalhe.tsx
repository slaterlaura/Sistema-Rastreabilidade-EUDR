import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowLeft, PenLine, RefreshCw, Sprout, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { CamposCadastraisFazenda, paraApi, type CamposFazenda } from "@/components/campos-fazenda";
import { Carregando, Dado, FaixaTitulo, Mensagem } from "@/components/comum";
import { Documentos } from "@/components/documentos";
import { CamadaDesenho, ControlesDesenho, useDesenho } from "@/components/editor-geometria";
import { Button } from "@/components/ui/button";
import {
  AjustarTamanho,
  AvisoCamada,
  CamadaSupressao,
  DefinicoesHachura,
  Enquadrar,
  GeometriaFazendaMapa,
  LegendaMapa,
  Mapa,
  type EstadoCamada,
} from "@/components/ui/fazendas-board-utils/mapa";
import { api } from "@/lib/api";
import { chaves, useFornecedores, useInvalidarCadastro } from "@/lib/consultas";
import { dataHora, ha, haDeM2 } from "@/lib/formato";
import { STATUS } from "@/lib/status";
import type { Fazenda } from "@/lib/tipos";

function camposDe(f: Fazenda): CamposFazenda {
  return {
    nome: f.nome,
    car_codigo: f.car_codigo ?? "",
    ccir: f.ccir ?? "",
    nirf: f.nirf ?? "",
    matricula: f.matricula ?? "",
    municipio: f.municipio ?? "",
    uf: f.uf ?? "",
    area_declarada_ha: f.area_declarada_ha ?? "",
  };
}

export default function PaginaFazenda() {
  const id = Number(useParams().id);
  const { data: fazenda, isLoading, error } = useQuery({
    queryKey: [...chaves.fazendas, id],
    queryFn: () => api.get<Fazenda>(`/fazendas/${id}`),
  });

  if (isLoading) return <Carregando />;
  if (error || !fazenda) return <Mensagem>{error?.message ?? "Fazenda não encontrada."}</Mensagem>;
  // key: ao trocar de fazenda, o estado da tela recomeça
  return <DetalheFazenda key={fazenda.id} fazenda={fazenda} />;
}

function DetalheFazenda({ fazenda }: { fazenda: Fazenda }) {
  const navegar = useNavigate();
  const [params, setParams] = useSearchParams();
  const recemCriada = params.get("nova") === "1";
  const invalidar = useInvalidarCadastro();
  const { data: fornecedores } = useFornecedores();
  const fornecedor = fornecedores?.find((f) => f.id === fazenda.fornecedor_id);
  const [editandoDados, setEditandoDados] = useState(false);
  const [redesenhando, setRedesenhando] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);
  const [estadoCamada, setEstadoCamada] = useState<EstadoCamada | null>(null);
  const aoMudarCamada = useCallback((e: EstadoCamada) => setEstadoCamada(e), []);
  const form = useForm<CamposFazenda>({ defaultValues: camposDe(fazenda) });
  const desenho = useDesenho(fazenda.geometry);
  const estilo = STATUS[fazenda.status];

  useEffect(() => {
    if (recemCriada) {
      const t = window.setTimeout(() => setParams({}, { replace: true }), 8000);
      return () => window.clearTimeout(t);
    }
  }, [recemCriada, setParams]);

  const salvar = useMutation({
    mutationFn: (corpo: unknown) => api.put<Fazenda>(`/fazendas/${fazenda.id}`, corpo),
    onSuccess: async (nova) => {
      if (nova.status !== fazenda.status) {
        setAviso(`Status mudou de ${STATUS[fazenda.status].rotulo} para ${STATUS[nova.status].rotulo} na nova verificação.`);
      }
      await invalidar();
    },
  });

  const verificar = useMutation({
    mutationFn: () => api.post<Fazenda>(`/fazendas/${fazenda.id}/verificar`),
    onSuccess: () => invalidar(),
  });

  const excluir = useMutation({
    mutationFn: () => api.delete(`/fazendas/${fazenda.id}`),
    onSuccess: async () => {
      await invalidar();
      navegar("/fazendas");
    },
  });

  const salvarDados = form.handleSubmit((campos) =>
    salvar.mutate(paraApi(campos), { onSuccess: () => setEditandoDados(false) }),
  );

  const sobreposicao = Number(fazenda.area_sobreposta_m2);
  const ehPonto = fazenda.geometry.type === "Point";
  const erro = salvar.error ?? verificar.error ?? excluir.error;

  return (
    <>
      <Link to="/fazendas" className="mb-3 inline-flex items-center gap-1 text-xs text-slate-500 hover:text-slate-950">
        <ArrowLeft size={13} aria-hidden="true" /> Fazendas
      </Link>
      <div className="grid min-h-[620px] grid-cols-1 overflow-hidden rounded-2xl border border-slate-200 bg-white lg:h-[calc(100dvh-170px)] lg:grid-cols-[420px_1fr]">
        <aside className="flex min-h-0 flex-col border-b border-slate-200 lg:border-r lg:border-b-0">
          <FaixaTitulo icone={<Sprout size={13} aria-hidden="true" />}>FAZENDA #{fazenda.id}</FaixaTitulo>
          <div className="min-h-0 flex-1 overflow-y-auto">
            <div className="space-y-4 px-5 py-4">
              <div>
                <h1 className="text-lg font-semibold text-slate-950">{fazenda.nome}</h1>
                <p className="text-sm text-slate-500">
                  {fornecedor ? <Link to={`/fornecedores/${fornecedor.id}`} className="hover:text-slate-950 hover:underline">{fornecedor.nome}</Link> : "—"}
                  {fazenda.municipio ? ` · ${fazenda.municipio}${fazenda.uf ? `/${fazenda.uf}` : ""}` : ""}
                </p>
              </div>

              {/* Status legível em dois segundos, pela cor (persona Roberto) */}
              <div className="rounded-xl border-2 px-4 py-3" style={{ borderColor: estilo.cor, backgroundColor: `${estilo.cor}10` }}>
                <div className="flex items-center justify-between gap-3">
                  <span className="font-mono text-xs font-medium tracking-widest" style={{ color: estilo.cor }}>
                    {estilo.rotulo.toUpperCase()}
                  </span>
                  <span className="font-mono text-[10px] text-slate-500">VERIFICADA {dataHora(fazenda.verificada_em)}</span>
                </div>
                <p className="mt-1 text-sm text-slate-700">
                  {fazenda.status === "bloqueada"
                    ? ehPonto
                      ? "O ponto cai dentro de área de supressão detectada depois de 31/12/2020. Não pode compor embarque."
                      : `${haDeM2(sobreposicao)} sobrepostos a supressão detectada depois de 31/12/2020. Não pode compor embarque.`
                    : fazenda.status === "apta"
                      ? sobreposicao > 0
                        ? `Sobreposição de ${haDeM2(sobreposicao)}, abaixo da tolerância de borda. Pode compor embarque.`
                        : "Sem sobreposição com supressão posterior a 31/12/2020. Pode compor embarque."
                      : "Aguardando verificação."}
                </p>
              </div>

              {recemCriada ? <Mensagem tipo="sucesso">Fazenda cadastrada e verificada contra a camada PRODES.</Mensagem> : null}
              {aviso ? <Mensagem tipo="aviso">{aviso}</Mensagem> : null}
              {erro ? <Mensagem>{erro.message}</Mensagem> : null}

              {redesenhando ? (
                <div className="space-y-3 rounded-xl border border-orange-200 bg-orange-50/40 p-3">
                  <p className="font-mono text-[10px] tracking-widest text-orange-800">REDESENHAR GEOMETRIA</p>
                  <ControlesDesenho desenho={desenho} areaDeclaradaHa={fazenda.area_declarada_ha ? Number(fazenda.area_declarada_ha) : null} />
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      variant="destaque"
                      disabled={!desenho.geometria || salvar.isPending}
                      onClick={() => salvar.mutate({ geometry: desenho.geometria }, { onSuccess: () => setRedesenhando(false) })}
                    >
                      {salvar.isPending ? "Verificando…" : "Salvar e reverificar"}
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => setRedesenhando(false)}>
                      Cancelar
                    </Button>
                  </div>
                </div>
              ) : null}

              {editandoDados ? (
                <form
                  onSubmit={salvarDados}
                  className="space-y-3"
                  noValidate
                >
                  <CamposCadastraisFazenda form={form} />
                  <div className="flex gap-2">
                    <Button size="sm" type="submit" disabled={salvar.isPending}>
                      Salvar dados
                    </Button>
                    <Button size="sm" type="button" variant="outline" onClick={() => setEditandoDados(false)}>
                      Cancelar
                    </Button>
                  </div>
                </form>
              ) : (
                <dl className="grid grid-cols-2 gap-x-4 gap-y-3">
                  <div className="col-span-2">
                    <Dado rotulo="CAR" mono>{fazenda.car_codigo ?? "não informado"}</Dado>
                  </div>
                  <Dado rotulo="Área declarada">{ha(fazenda.area_declarada_ha)}</Dado>
                  <Dado rotulo="Geometria">{ehPonto ? "Ponto" : fazenda.geometry.type === "MultiPolygon" ? "Multipolígono" : "Polígono"}</Dado>
                  <Dado rotulo="CCIR">{fazenda.ccir ?? "—"}</Dado>
                  <Dado rotulo="NIRF">{fazenda.nirf ?? "—"}</Dado>
                  <Dado rotulo="Matrícula">{fazenda.matricula ?? "—"}</Dado>
                  <Dado rotulo="Camada de referência">{fazenda.camada_versao_id ? `versão #${fazenda.camada_versao_id}` : "—"}</Dado>
                </dl>
              )}

              <div className="flex flex-wrap gap-2">
                {!editandoDados ? (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      form.reset(camposDe(fazenda));
                      setEditandoDados(true);
                    }}
                  >
                    <PenLine aria-hidden="true" /> Editar dados
                  </Button>
                ) : null}
                {!redesenhando ? (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      desenho.reiniciar(fazenda.geometry);
                      setAviso(null);
                      setRedesenhando(true);
                    }}
                  >
                    <PenLine aria-hidden="true" /> Redesenhar
                  </Button>
                ) : null}
                <Button size="sm" variant="ghost" onClick={() => verificar.mutate()} disabled={verificar.isPending}>
                  <RefreshCw className={verificar.isPending ? "animate-spin" : ""} aria-hidden="true" /> Reprocessar
                </Button>
                <Button
                  size="sm"
                  variant="destructive"
                  disabled={excluir.isPending}
                  onClick={() => {
                    if (window.confirm(`Excluir a fazenda "${fazenda.nome}" e seus documentos?`)) excluir.mutate();
                  }}
                >
                  <Trash2 aria-hidden="true" /> Excluir
                </Button>
              </div>
            </div>
            <div className="border-t border-slate-200">
              <Documentos dono="fazendas" id={fazenda.id} />
            </div>
          </div>
        </aside>
        <div className="relative min-h-[420px]">
          <DefinicoesHachura />
          <Mapa>
            <AjustarTamanho />
            <Enquadrar geometrias={[fazenda.geometry]} chave={`${fazenda.id}-${fazenda.atualizado_em}`} />
            <CamadaSupressao visivel onEstado={aoMudarCamada} />
            {redesenhando ? (
              <>
                <GeometriaFazendaMapa geometria={fazenda.geometry} status={fazenda.status} esmaecida />
                <CamadaDesenho desenho={desenho} />
              </>
            ) : (
              <GeometriaFazendaMapa geometria={fazenda.geometry} status={fazenda.status} rotulo={fazenda.nome} />
            )}
          </Mapa>
          <div className="pointer-events-none absolute top-3 right-16 left-14 z-[500] flex flex-wrap gap-2">
            <AvisoCamada estado={estadoCamada} visivel />
          </div>
          <div className="pointer-events-none absolute bottom-6 left-3 z-[500] hidden sm:block">
            <LegendaMapa />
          </div>
        </div>
      </div>
    </>
  );
}
