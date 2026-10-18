import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Ban, Download, FileCheck2, Lock, Package, Save } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Carregando, Dado, FaixaTitulo, Mensagem, StatusPill } from "@/components/comum";
import { Button } from "@/components/ui/button";
import {
  AjustarTamanho,
  CamadaSupressao,
  DefinicoesHachura,
  Enquadrar,
  GeometriaFazendaMapa,
  LegendaMapa,
  Mapa,
} from "@/components/ui/fazendas-board-utils/mapa";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { chaves, useEmbarque, useFazendas, useFornecedores } from "@/lib/consultas";
import { data, dataHora, haDeM2, kg } from "@/lib/formato";
import { STATUS } from "@/lib/status";
import type { Embarque, Fazenda } from "@/lib/tipos";
import { cn } from "@/lib/utils";
import { SeloEmbarque } from "@/pages/embarques";

export default function PaginaEmbarque() {
  const id = Number(useParams().id);
  const { data: embarque, isLoading, error } = useEmbarque(id);
  if (isLoading) return <Carregando />;
  if (error || !embarque) return <Mensagem>{error?.message ?? "Embarque não encontrado."}</Mensagem>;
  return <DetalheEmbarque key={`${embarque.id}-${embarque.status}`} embarque={embarque} />;
}

function quantidadesDe(e: Embarque): Record<number, string> {
  return Object.fromEntries(e.parcelas.map((p) => [p.fazenda_id, String(Number(p.quantidade_kg))]));
}

/** Por que a fazenda não pode entrar no embarque (visível, nunca oculta: context.md §13). */
function motivoRecusa(f: Fazenda): string | null {
  if (f.status === "apta") return null;
  if (f.status === "pendente") return "Aguardando verificação";
  return f.geometry.type === "Point"
    ? "Bloqueada: ponto dentro de supressão pós-2020"
    : `Bloqueada: ${haDeM2(f.area_sobreposta_m2, 2)} sobre supressão pós-2020`;
}

function DetalheEmbarque({ embarque }: { embarque: Embarque }) {
  const [aba, setAba] = useState<"composicao" | "evidencias">(embarque.status === "fechado" ? "evidencias" : "composicao");
  const fechado = embarque.status === "fechado";

  return (
    <>
      <Link to="/embarques" className="mb-3 inline-flex items-center gap-1 text-xs text-slate-500 hover:text-slate-950">
        <ArrowLeft size={13} aria-hidden="true" /> Embarques
      </Link>
      <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="font-mono text-xl font-semibold tracking-tight text-slate-950">{embarque.identificacao}</h1>
            <SeloEmbarque status={embarque.status} />
          </div>
          <p className="mt-1 text-sm text-slate-500">
            {embarque.destino} · embarque em {data(embarque.data_embarque)}
            {fechado ? ` · fechado em ${dataHora(embarque.fechado_em)}` : ""}
          </p>
        </div>
        <div role="tablist" aria-label="Seções do embarque" className="flex gap-1.5">
          {(
            [
              ["composicao", "Composição"],
              ["evidencias", "Evidências"],
            ] as const
          ).map(([valor, rotulo]) => (
            <button
              key={valor}
              role="tab"
              type="button"
              aria-selected={aba === valor}
              onClick={() => setAba(valor)}
              className={cn(
                "rounded-full border px-3 py-1 text-xs font-medium",
                aba === valor ? "border-slate-950 bg-slate-950 text-white" : "border-slate-200 bg-white text-slate-600 hover:text-slate-950",
              )}
            >
              {rotulo}
            </button>
          ))}
        </div>
      </div>
      {aba === "composicao" ? <Composicao embarque={embarque} /> : <Evidencias embarque={embarque} />}
    </>
  );
}

function Composicao({ embarque }: { embarque: Embarque }) {
  const queryClient = useQueryClient();
  const { data: fazendas, isLoading } = useFazendas();
  const { data: fornecedores } = useFornecedores();
  const nomeFornecedor = useMemo(() => new Map((fornecedores ?? []).map((f) => [f.id, f.nome])), [fornecedores]);
  const fechado = embarque.status === "fechado";

  const inicial = useMemo(() => quantidadesDe(embarque), [embarque]);
  const [quantidades, setQuantidades] = useState<Record<number, string>>(inicial);
  const selecionadas = Object.keys(quantidades).map(Number);
  const alterado = JSON.stringify(quantidades) !== JSON.stringify(inicial);
  const total = selecionadas.reduce((s, id) => s + (Number(quantidades[id].replace(",", ".")) || 0), 0);

  const invalidarEmbarque = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: [...chaves.embarques, embarque.id] }),
      queryClient.invalidateQueries({ queryKey: chaves.embarques }),
      queryClient.invalidateQueries({ queryKey: chaves.dossies }),
    ]);

  const salvar = useMutation({
    mutationFn: () =>
      api.put<Embarque>(`/embarques/${embarque.id}/parcelas`, {
        parcelas: selecionadas.map((id) => ({ fazenda_id: id, quantidade_kg: Number(quantidades[id].replace(",", ".")) })),
      }),
    onSuccess: (atualizado) => {
      setQuantidades(quantidadesDe(atualizado)); // normaliza "12,5" -> "12.5" para não parecer alterado
      return invalidarEmbarque();
    },
  });

  const fechar = useMutation({
    mutationFn: () => api.post<Embarque>(`/embarques/${embarque.id}/fechar`),
    onSuccess: invalidarEmbarque,
  });

  const quantidadeInvalida = selecionadas.some((id) => !(Number(quantidades[id].replace(",", ".")) > 0));
  const incluidasNaoAptas = (fazendas ?? []).filter((f) => selecionadas.includes(f.id) && f.status !== "apta");

  // Aptas primeiro; as recusadas continuam visíveis, desabilitadas, com o motivo ao lado.
  const ordenadas = [...(fazendas ?? [])].sort(
    (a, b) => Number(a.status !== "apta") - Number(b.status !== "apta") || a.nome.localeCompare(b.nome),
  );
  const lista = fechado ? ordenadas.filter((f) => selecionadas.includes(f.id)) : ordenadas;
  const geometriasSelecionadas = (fazendas ?? []).filter((f) => selecionadas.includes(f.id));

  return (
    <div className="grid min-h-[600px] grid-cols-1 overflow-hidden rounded-2xl border border-slate-200 bg-white lg:h-[calc(100dvh-240px)] lg:grid-cols-[440px_1fr]">
      <aside className="flex min-h-0 flex-col border-b border-slate-200 lg:border-r lg:border-b-0">
        <FaixaTitulo icone={<Package size={13} aria-hidden="true" />}>{fechado ? "PARCELAS (CONGELADAS)" : "PARCELAS"}</FaixaTitulo>
        {fechado ? (
          <div className="border-b border-slate-200 px-4 py-2">
            <p className="flex items-center gap-1.5 text-xs text-slate-600">
              <Lock size={12} aria-hidden="true" /> Embarque fechado. A composição não pode mais mudar.
            </p>
          </div>
        ) : null}
        {isLoading ? <Carregando /> : null}
        <ul className="max-h-96 min-h-0 flex-1 overflow-y-auto p-2 lg:max-h-none">
          {lista.map((f) => {
            const motivo = motivoRecusa(f);
            const incluida = f.id in quantidades;
            const desabilitada = fechado || (motivo !== null && !incluida);
            return (
              <li key={f.id} className={cn("rounded-lg px-3 py-2", incluida && "bg-orange-50", desabilitada && !incluida && "opacity-70")}>
                <div className="flex items-center gap-3">
                  <input
                    type="checkbox"
                    className="size-4 shrink-0 accent-slate-950"
                    checked={incluida}
                    disabled={desabilitada}
                    aria-label={`Incluir ${f.nome}`}
                    onChange={(e) =>
                      setQuantidades((q) => {
                        const nova = { ...q };
                        if (e.target.checked) nova[f.id] = "";
                        else delete nova[f.id];
                        return nova;
                      })
                    }
                  />
                  <span className="min-w-0 flex-1">
                    <span className={cn("block truncate text-sm font-medium", incluida ? "text-orange-800" : "text-slate-950")}>{f.nome}</span>
                    <span className="block truncate text-xs text-slate-500">{nomeFornecedor.get(f.fornecedor_id) ?? "—"}</span>
                  </span>
                  {incluida && !fechado ? (
                    <label className="flex shrink-0 items-center gap-1">
                      <span className="sr-only">Quantidade de {f.nome} em kg</span>
                      <Input
                        inputMode="decimal"
                        placeholder="0"
                        value={quantidades[f.id]}
                        onChange={(e) => setQuantidades((q) => ({ ...q, [f.id]: e.target.value }))}
                        className="h-8 w-24 text-right font-mono text-xs"
                        aria-invalid={!(Number(quantidades[f.id].replace(",", ".")) > 0)}
                      />
                      <span className="font-mono text-[10px] text-slate-500">KG</span>
                    </label>
                  ) : incluida ? (
                    <span className="shrink-0 font-mono text-xs text-slate-950">{kg(quantidades[f.id])}</span>
                  ) : (
                    <StatusPill status={f.status} />
                  )}
                </div>
                {motivo ? (
                  <p className="mt-1 flex items-center gap-1.5 pl-7 font-mono text-[10px]" style={{ color: STATUS[f.status].cor }}>
                    <Ban size={11} aria-hidden="true" /> {motivo.toUpperCase()}
                    {incluida ? " · REMOVA PARA FECHAR" : ""}
                  </p>
                ) : null}
              </li>
            );
          })}
          {fazendas?.length === 0 ? (
            <li className="px-3 py-6 text-center text-sm text-slate-500">
              Nenhuma fazenda cadastrada. <Link to="/fazendas/nova" className="underline">Cadastre uma</Link>.
            </li>
          ) : null}
        </ul>
        <div className="space-y-2 border-t border-slate-200 px-4 py-3">
          <p className="font-mono text-[10px] text-slate-500">
            {selecionadas.length} PARCELA(S) · TOTAL {kg(total).toUpperCase()}
            {alterado && !fechado ? " · ALTERAÇÕES NÃO SALVAS" : ""}
          </p>
          {salvar.error ? <Mensagem>{salvar.error.message}</Mensagem> : null}
          {fechar.error ? <Mensagem>{fechar.error.message}</Mensagem> : null}
          {incluidasNaoAptas.length && !fechado ? (
            <Mensagem tipo="aviso">
              {incluidasNaoAptas.map((f) => f.nome).join(", ")} deixou de estar apta depois de entrar no embarque. Remova para poder fechar.
            </Mensagem>
          ) : null}
          {!fechado ? (
            <div className="flex gap-2">
              <Button size="sm" variant="outline" disabled={!alterado || quantidadeInvalida || salvar.isPending} onClick={() => salvar.mutate()}>
                <Save aria-hidden="true" /> {salvar.isPending ? "Salvando…" : "Salvar composição"}
              </Button>
              <Button
                size="sm"
                variant="destaque"
                className="flex-1"
                disabled={alterado || embarque.parcelas.length === 0 || fechar.isPending}
                title={alterado ? "Salve a composição antes de fechar" : undefined}
                onClick={() => {
                  if (
                    window.confirm(
                      "Fechar o embarque? Os dados das fazendas serão congelados no dossiê e a composição não poderá mais mudar.",
                    )
                  ) {
                    fechar.mutate();
                  }
                }}
              >
                <Lock aria-hidden="true" /> {fechar.isPending ? "Gerando dossiê…" : "Fechar e gerar dossiê"}
              </Button>
            </div>
          ) : null}
        </div>
      </aside>
      <div className="relative min-h-[380px]">
        <DefinicoesHachura />
        <Mapa>
          <AjustarTamanho />
          <Enquadrar
            geometrias={(geometriasSelecionadas.length ? geometriasSelecionadas : fazendas ?? []).map((f) => f.geometry)}
            chave={`${embarque.id}-${fazendas?.length ?? 0}`}
          />
          <CamadaSupressao visivel />
          {(fazendas ?? []).map((f) => (
            <GeometriaFazendaMapa
              key={f.id}
              geometria={f.geometry}
              status={f.status}
              rotulo={f.nome}
              selecionada={selecionadas.includes(f.id)}
              esmaecida={!selecionadas.includes(f.id)}
            />
          ))}
        </Mapa>
        <div className="pointer-events-none absolute bottom-6 left-3 z-[500] hidden sm:block">
          <LegendaMapa />
        </div>
      </div>
    </div>
  );
}

function Evidencias({ embarque }: { embarque: Embarque }) {
  const [erro, setErro] = useState<string | null>(null);
  if (!embarque.dossie_id) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white">
        <FaixaTitulo icone={<FileCheck2 size={13} aria-hidden="true" />}>EVIDÊNCIAS</FaixaTitulo>
        <p className="px-5 py-8 text-center text-sm text-slate-500">
          O dossiê de origem é gerado ao fechar o embarque, com GeoJSON (para o sistema do importador) e PDF.
        </p>
      </div>
    );
  }
  const baixar = async (formato: "geojson" | "pdf") => {
    setErro(null);
    try {
      await api.baixar(`/dossies/${embarque.dossie_id}/${formato}`, `dossie-${embarque.identificacao}.${formato}`);
    } catch (e) {
      setErro((e as Error).message);
    }
  };
  return (
    <div className="rounded-2xl border border-slate-200 bg-white">
      <FaixaTitulo icone={<FileCheck2 size={13} aria-hidden="true" />}>DOSSIÊ #{embarque.dossie_id}</FaixaTitulo>
      <div className="space-y-4 px-5 py-4">
        <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <Dado rotulo="Parcelas">{embarque.parcelas.length}</Dado>
          <Dado rotulo="Total">{kg(embarque.total_kg)}</Dado>
          <Dado rotulo="Destino">{embarque.destino}</Dado>
          <Dado rotulo="Fechado em">{dataHora(embarque.fechado_em)}</Dado>
        </dl>
        <p className="text-sm text-slate-600">
          O GeoJSON é a evidência principal para o importador: é processável pelo sistema dele. O PDF é a versão legível.
        </p>
        {erro ? <Mensagem>{erro}</Mensagem> : null}
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => baixar("geojson")}>
            <Download aria-hidden="true" /> Baixar GeoJSON
          </Button>
          <Button variant="outline" onClick={() => baixar("pdf")}>
            <Download aria-hidden="true" /> Baixar PDF
          </Button>
          <Button asChild variant="ghost">
            <Link to={`/dossies/${embarque.dossie_id}`}>Ver retrato congelado</Link>
          </Button>
        </div>
      </div>
    </div>
  );
}
