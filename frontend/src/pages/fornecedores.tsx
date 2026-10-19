import { useMutation } from "@tanstack/react-query";
import { ChevronRight, Plus, Users } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate } from "react-router-dom";
import { CamposCadastraisFornecedor, fornecedorParaApi, fornecedorVazio, type CamposFornecedor } from "@/components/campos-fornecedor";
import { CabecalhoPagina, Carregando, FaixaTitulo, Mensagem, Painel } from "@/components/comum";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { useFazendas, useFornecedores, useInvalidarCadastro } from "@/lib/consultas";
import { documento } from "@/lib/formato";
import { STATUS } from "@/lib/status";
import type { Fornecedor } from "@/lib/tipos";

export default function PaginaFornecedores() {
  const { data: fornecedores, isLoading, error } = useFornecedores();
  const { data: fazendas } = useFazendas();
  const [criando, setCriando] = useState(false);

  const bloqueadasPorFornecedor = new Map<number, number>();
  for (const f of fazendas ?? []) {
    if (f.status === "bloqueada") bloqueadasPorFornecedor.set(f.fornecedor_id, (bloqueadasPorFornecedor.get(f.fornecedor_id) ?? 0) + 1);
  }

  return (
    <>
      <CabecalhoPagina
        titulo="Fornecedores"
        subtitulo="Produtores e cooperativas que vendem para você. Cada um pode ter várias fazendas."
        acoes={
          <Button size="sm" onClick={() => setCriando((v) => !v)} aria-expanded={criando}>
            <Plus aria-hidden="true" /> Novo fornecedor
          </Button>
        }
      />
      {criando ? <NovoFornecedor aoCancelar={() => setCriando(false)} /> : null}
      {error ? <Mensagem>{error.message}</Mensagem> : null}
      <Painel>
        <FaixaTitulo icone={<Users size={13} aria-hidden="true" />}>FORNECEDORES</FaixaTitulo>
        {isLoading ? <Carregando /> : null}
        <ul className="divide-y divide-slate-100">
          {fornecedores?.map((f) => {
            const bloqueadas = bloqueadasPorFornecedor.get(f.id) ?? 0;
            return (
              <li key={f.id}>
                <Link to={`/fornecedores/${f.id}`} className="flex items-center gap-4 px-5 py-3 hover:bg-slate-50">
                  <span className="w-10 shrink-0 font-mono text-[10px] text-slate-500">{f.tipo_pessoa}</span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium text-slate-950">{f.nome}</span>
                    <span className="block truncate font-mono text-[11px] text-slate-500">
                      {documento(f.documento)}
                      {f.municipio ? ` · ${f.municipio}${f.uf ? `/${f.uf}` : ""}` : ""}
                    </span>
                  </span>
                  <span className="shrink-0 text-right">
                    <span className="block font-mono text-[11px] text-slate-600">{f.total_fazendas} FAZENDA(S)</span>
                    {bloqueadas ? (
                      <span className="block font-mono text-[10px]" style={{ color: STATUS.bloqueada.cor }}>
                        {bloqueadas} BLOQUEADA(S)
                      </span>
                    ) : null}
                  </span>
                  <ChevronRight size={16} className="shrink-0 text-slate-400" aria-hidden="true" />
                </Link>
              </li>
            );
          })}
          {fornecedores?.length === 0 ? (
            <li className="px-5 py-8 text-center text-sm text-slate-500">Nenhum fornecedor ainda. Comece cadastrando um.</li>
          ) : null}
        </ul>
      </Painel>
    </>
  );
}

function NovoFornecedor({ aoCancelar }: { aoCancelar: () => void }) {
  const navegar = useNavigate();
  const invalidar = useInvalidarCadastro();
  const form = useForm<CamposFornecedor>({ defaultValues: fornecedorVazio });
  const criar = useMutation({
    mutationFn: (corpo: unknown) => api.post<Fornecedor>("/fornecedores", corpo),
    onSuccess: async (f) => {
      await invalidar();
      navegar(`/fornecedores/${f.id}`);
    },
  });
  return (
    <Painel className="mb-4">
      <FaixaTitulo icone={<Plus size={13} aria-hidden="true" />}>NOVO FORNECEDOR</FaixaTitulo>
      <form onSubmit={form.handleSubmit((c) => criar.mutate(fornecedorParaApi(c)))} className="space-y-3 px-5 py-4" noValidate>
        <CamposCadastraisFornecedor form={form} />
        {criar.error ? <Mensagem>{criar.error.message}</Mensagem> : null}
        <div className="flex gap-2">
          <Button type="submit" size="sm" disabled={criar.isPending}>
            Salvar fornecedor
          </Button>
          <Button type="button" size="sm" variant="outline" onClick={aoCancelar}>
            Cancelar
          </Button>
        </div>
      </form>
    </Painel>
  );
}
