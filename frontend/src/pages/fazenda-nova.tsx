import { useMutation } from "@tanstack/react-query";
import { Sprout } from "lucide-react";
import { useCallback, useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate, useSearchParams } from "react-router-dom";
import { CamposCadastraisFazenda, camposVazios, paraApi, type CamposFazenda } from "@/components/campos-fazenda";
import { CabecalhoPagina, Campo, FaixaTitulo, Mensagem } from "@/components/comum";
import { CamadaDesenho, ControlesDesenho, useDesenho } from "@/components/editor-geometria";
import { Button } from "@/components/ui/button";
import {
  AjustarTamanho,
  AvisoCamada,
  CamadaImoveis,
  CamadaSupressao,
  DefinicoesHachura,
  Enquadrar,
  GeometriaFazendaMapa,
  LegendaMapa,
  Mapa,
  type EstadoCamada,
} from "@/components/ui/fazendas-board-utils/mapa";
import { Select } from "@/components/ui/input";
import { api } from "@/lib/api";
import { useFazendas, useFornecedores, useInvalidarCadastro } from "@/lib/consultas";
import type { Fazenda, ImovelDetalhe, ImovelResumo } from "@/lib/tipos";

export default function PaginaNovaFazenda() {
  const navegar = useNavigate();
  const [params] = useSearchParams();
  const { data: fornecedores } = useFornecedores();
  const { data: fazendas } = useFazendas();
  const invalidar = useInvalidarCadastro();
  const [fornecedorId, setFornecedorId] = useState(params.get("fornecedor") ?? "");
  const form = useForm<CamposFazenda>({ defaultValues: camposVazios });
  const desenho = useDesenho();
  const [estadoCamada, setEstadoCamada] = useState<EstadoCamada | null>(null);
  const aoMudarCamada = useCallback((e: EstadoCamada) => setEstadoCamada(e), []);
  const [estadoImoveis, setEstadoImoveis] = useState<EstadoCamada | null>(null);
  const aoMudarImoveis = useCallback((e: EstadoCamada) => setEstadoImoveis(e), []);
  const [erroImovel, setErroImovel] = useState<string | null>(null);
  const modoImovel = desenho.modo === "imovel";

  /** Adota um imóvel do CAR: o desenho e os dados cadastrais vêm da base comum. */
  async function escolherImovel(resumo: ImovelResumo) {
    setErroImovel(null);
    try {
      const imovel = await api.get<ImovelDetalhe>(`/imoveis/${encodeURIComponent(resumo.cod_imovel)}`);
      desenho.adotar(imovel);
      const opcoes = { shouldDirty: true, shouldValidate: form.formState.isSubmitted };
      form.setValue("car_codigo", imovel.cod_imovel, opcoes);
      if (imovel.municipio) form.setValue("municipio", imovel.municipio, opcoes);
      if (imovel.uf) form.setValue("uf", imovel.uf, opcoes);
      if (imovel.area_ha != null) form.setValue("area_declarada_ha", String(imovel.area_ha), opcoes);
      if (!form.getValues("nome")) {
        form.setValue("nome", `Imóvel ${imovel.municipio ?? ""} ${imovel.cod_imovel.slice(-6)}`.replace(/\s+/g, " ").trim(), opcoes);
      }
    } catch (e) {
      setErroImovel((e as Error).message);
    }
  }

  const criar = useMutation({
    mutationFn: (corpo: unknown) => api.post<Fazenda>("/fazendas", corpo),
    onSuccess: async (fazenda) => {
      await invalidar();
      navegar(`/fazendas/${fazenda.id}?nova=1`);
    },
  });

  const enviar = form.handleSubmit((campos) => {
    if (!fornecedorId) return;
    if (!desenho.geometria) return;
    criar.mutate({ fornecedor_id: Number(fornecedorId), ...paraApi(campos), geometry: desenho.geometria });
  });

  const faltaGeometria = form.formState.isSubmitted && !desenho.geometria;
  const faltaFornecedor = form.formState.isSubmitted && !fornecedorId;
  const areaDeclarada = Number((form.watch("area_declarada_ha") || "0").replace(",", "."));

  return (
    <>
      <CabecalhoPagina
        titulo="Nova fazenda"
        subtitulo="A verificação contra o PRODES roda ao salvar; o status aparece em seguida."
      />
      <div className="grid min-h-[620px] grid-cols-1 overflow-hidden rounded-2xl border border-slate-200 bg-white lg:h-[calc(100dvh-190px)] lg:grid-cols-[400px_1fr]">
        <aside className="flex min-h-0 flex-col border-b border-slate-200 lg:border-r lg:border-b-0">
          <FaixaTitulo icone={<Sprout size={13} aria-hidden="true" />}>CADASTRO E DESENHO</FaixaTitulo>
          <form onSubmit={enviar} className="min-h-0 flex-1 space-y-5 overflow-y-auto px-5 py-4" noValidate>
            <Campo rotulo="Fornecedor" erro={faltaFornecedor ? "Escolha o fornecedor." : undefined}>
              <Select value={fornecedorId} onChange={(e) => setFornecedorId(e.target.value)} aria-invalid={faltaFornecedor}>
                <option value="">Escolha…</option>
                {fornecedores?.map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.nome}
                  </option>
                ))}
              </Select>
            </Campo>
            {fornecedores?.length === 0 ? (
              <Mensagem tipo="aviso">Cadastre um fornecedor antes da fazenda.</Mensagem>
            ) : null}

            <div className="space-y-2">
              <p className="font-mono text-[10px] tracking-widest text-slate-500">GEOMETRIA</p>
              <ControlesDesenho desenho={desenho} areaDeclaradaHa={areaDeclarada || null} />
              {faltaGeometria ? (
                <p className="text-xs text-red-700">
                  {modoImovel
                    ? "Clique num imóvel do CAR no mapa."
                    : desenho.modo === "ponto"
                      ? "Marque o ponto no mapa."
                      : "Desenhe o contorno com pelo menos 3 vértices."}
                </p>
              ) : null}
              {erroImovel ? <Mensagem>{erroImovel}</Mensagem> : null}
            </div>

            <div className="space-y-2">
              <p className="font-mono text-[10px] tracking-widest text-slate-500">DADOS CADASTRAIS</p>
              <CamposCadastraisFazenda form={form} />
            </div>

            {criar.error ? <Mensagem>{criar.error.message}</Mensagem> : null}
            <div className="flex gap-2 pb-2">
              <Button type="submit" disabled={criar.isPending} className="flex-1">
                {criar.isPending ? "Salvando e verificando…" : "Salvar e verificar"}
              </Button>
              <Button type="button" variant="outline" onClick={() => navegar("/fazendas")}>
                Cancelar
              </Button>
            </div>
          </form>
        </aside>
        <div className="relative min-h-[420px]">
          <DefinicoesHachura />
          <Mapa>
            <AjustarTamanho />
            <Enquadrar geometrias={(fazendas ?? []).map((f) => f.geometry)} chave={String(fazendas?.length ?? 0)} zoomMaximo={14} />
            <CamadaSupressao visivel onEstado={aoMudarCamada} />
            <CamadaImoveis
              visivel={modoImovel}
              onEstado={aoMudarImoveis}
              onSelecionar={escolherImovel}
              selecionado={desenho.imovel?.cod_imovel ?? null}
            />
            {fazendas?.map((f) => (
              <GeometriaFazendaMapa key={f.id} geometria={f.geometry} status={f.status} rotulo={f.nome} esmaecida />
            ))}
            <CamadaDesenho desenho={desenho} />
          </Mapa>
          <div className="pointer-events-none absolute top-3 right-16 left-14 z-[500] flex flex-wrap gap-2">
            <AvisoCamada estado={estadoCamada} visivel />
            <AvisoCamada estado={estadoImoveis} visivel={modoImovel} nome="imóveis do CAR" />
          </div>
          <div className="pointer-events-none absolute bottom-6 left-3 z-[500] hidden sm:block">
            <LegendaMapa comImoveis={modoImovel} />
          </div>
        </div>
      </div>
    </>
  );
}
