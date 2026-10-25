import { useMutation } from "@tanstack/react-query";
import { ChevronRight, Plus, Ship } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate } from "react-router-dom";
import { CabecalhoPagina, Campo, Carregando, FaixaTitulo, Mensagem, Painel } from "@/components/comum";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { chaves, useEmbarques } from "@/lib/consultas";
import { data, kg } from "@/lib/formato";
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

interface CamposEmbarque {
  identificacao: string;
  data_embarque: string;
  destino: string;
}

function NovoEmbarque({ aoCancelar }: { aoCancelar: () => void }) {
  const navegar = useNavigate();
  const queryClient = useQueryClient();
  const form = useForm<CamposEmbarque>();
  const criar = useMutation({
    mutationFn: (corpo: CamposEmbarque) => api.post<Embarque>("/embarques", corpo),
    onSuccess: async (e) => {
      await queryClient.invalidateQueries({ queryKey: chaves.embarques });
      navegar(`/embarques/${e.id}`);
    },
  });
  const erros = form.formState.errors;
  return (
    <Painel className="mb-4">
      <FaixaTitulo icone={<Plus size={13} aria-hidden="true" />}>NOVO EMBARQUE</FaixaTitulo>
      <form onSubmit={form.handleSubmit((c) => criar.mutate(c))} className="space-y-3 px-5 py-4" noValidate>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-[1fr_170px_1fr]">
          <Campo rotulo="Identificação" erro={erros.identificacao?.message} dica="Ex.: número do contrato ou da reserva">
            <Input className="font-mono text-xs" {...form.register("identificacao", { required: "Informe a identificação." })} />
          </Campo>
          <Campo rotulo="Data do embarque" erro={erros.data_embarque?.message}>
            <Input type="date" {...form.register("data_embarque", { required: "Informe a data." })} />
          </Campo>
          <Campo rotulo="Destino" erro={erros.destino?.message} dica="Porto e país na União Europeia">
            <Input {...form.register("destino", { required: "Informe o destino." })} />
          </Campo>
        </div>
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
