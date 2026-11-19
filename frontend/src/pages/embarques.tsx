import { useMutation } from "@tanstack/react-query";
import { ChevronRight, Plus, Ship } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate } from "react-router-dom";
import { CamposDoEmbarque, embarqueParaApi, embarqueVazio, type CamposEmbarque } from "@/components/campos-embarque";
import { CabecalhoPagina, Carregando, FaixaTitulo, Mensagem, Painel } from "@/components/comum";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { chaves, useEmbarques } from "@/lib/consultas";
import { data, kg } from "@/lib/formato";
import { textoEspecificacao } from "@/lib/produtos";
import type { Embarque } from "@/lib/tipos";
import { cn } from "@/lib/utils";
import { useQueryClient } from "@tanstack/react-query";

export function SeloEmbarque({ status }: { status: Embarque["status"] }) {
  return (
    <span
      className={cn(
        "rounded-full border px-2 py-0.5 font-mono text-[10px]",
        status === "fechado" ? "border-slate-950 bg-slate-950 text-white" : "border-slate-300 text-slate-600",
      )}
    >
      {status.toUpperCase()}
    </span>
  );
}

export default function PaginaEmbarques() {
  const { data: embarques, isLoading, error } = useEmbarques();
  const [criando, setCriando] = useState(false);
  return (
    <>
      <CabecalhoPagina
        titulo="Embarques"
        subtitulo="Cada embarque reúne parcelas de fazendas aptas. Ao fechar, o dossiê de origem é gerado e congelado."
        acoes={
          <Button size="sm" onClick={() => setCriando((v) => !v)} aria-expanded={criando}>
            <Plus aria-hidden="true" /> Novo embarque
          </Button>
        }
      />
      {criando ? <NovoEmbarque aoCancelar={() => setCriando(false)} /> : null}
      {error ? <Mensagem>{error.message}</Mensagem> : null}
      <Painel>
        <FaixaTitulo icone={<Ship size={13} aria-hidden="true" />}>EMBARQUES</FaixaTitulo>
        {isLoading ? <Carregando /> : null}
        <ul className="divide-y divide-slate-100">
          {embarques?.map((e) => (
            <li key={e.id}>
              <Link to={`/embarques/${e.id}`} className="flex items-center gap-4 px-5 py-3 hover:bg-slate-50">
                <span className="w-20 shrink-0 font-mono text-[11px] text-slate-500">{data(e.data_embarque)}</span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-mono text-sm font-medium text-slate-950">{e.identificacao}</span>
                  <span className="block truncate text-xs text-slate-500">
                    {e.destino} · {e.parcelas.length} parcela(s) · {kg(e.total_kg)}
                  </span>
                  <span className="block truncate text-xs text-slate-500">
                    {e.produto ? (
                      <>
                        {e.produto.descricao}
                        {textoEspecificacao(e) ? ` · ${textoEspecificacao(e)}` : ""}
                      </>
                    ) : (
                      <span className="text-amber-700">Produto não informado</span>
                    )}
                  </span>
                </span>
                <SeloEmbarque status={e.status} />
                <ChevronRight size={16} className="shrink-0 text-slate-400" aria-hidden="true" />
              </Link>
            </li>
          ))}
          {embarques?.length === 0 ? (
            <li className="px-5 py-8 text-center text-sm text-slate-500">Nenhum embarque ainda.</li>
          ) : null}
        </ul>
      </Painel>
    </>
  );
}

function NovoEmbarque({ aoCancelar }: { aoCancelar: () => void }) {
  const navegar = useNavigate();
  const queryClient = useQueryClient();
  const form = useForm<CamposEmbarque>({ defaultValues: embarqueVazio });
  const criar = useMutation({
    mutationFn: (campos: CamposEmbarque) => api.post<Embarque>("/embarques", embarqueParaApi(campos)),
    onSuccess: async (e) => {
      await queryClient.invalidateQueries({ queryKey: chaves.embarques });
      navegar(`/embarques/${e.id}`);
    },
  });
  return (
    <Painel className="mb-4">
      <FaixaTitulo icone={<Plus size={13} aria-hidden="true" />}>NOVO EMBARQUE</FaixaTitulo>
      <form onSubmit={form.handleSubmit((c) => criar.mutate(c))} className="space-y-3 px-5 py-4" noValidate>
        <CamposDoEmbarque form={form} />
        {criar.error ? <Mensagem>{criar.error.message}</Mensagem> : null}
        <div className="flex gap-2">
          <Button type="submit" size="sm" disabled={criar.isPending}>
            Criar rascunho
          </Button>
          <Button type="button" size="sm" variant="outline" onClick={aoCancelar}>
            Cancelar
          </Button>
        </div>
      </form>
    </Painel>
  );
}
