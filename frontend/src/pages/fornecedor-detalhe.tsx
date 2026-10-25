import { useMutation } from "@tanstack/react-query";
import { ArrowLeft, PenLine, Plus, Sprout, Trash2, Users } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate, useParams } from "react-router-dom";
import { CamposCadastraisFornecedor, camposDeFornecedor, fornecedorParaApi, type CamposFornecedor } from "@/components/campos-fornecedor";
import { Carregando, Dado, FaixaTitulo, Mensagem, Painel, StatusPill } from "@/components/comum";
import { Documentos } from "@/components/documentos";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { useFazendas, useFornecedores, useInvalidarCadastro } from "@/lib/consultas";
import { documento, ha } from "@/lib/formato";
import type { Fornecedor } from "@/lib/tipos";

export default function PaginaFornecedor() {
  const id = Number(useParams().id);
  const { data: fornecedores, isLoading, error } = useFornecedores();
  const fornecedor = fornecedores?.find((f) => f.id === id);
  if (isLoading) return <Carregando />;
  if (error || !fornecedor) return <Mensagem>{error?.message ?? "Fornecedor não encontrado."}</Mensagem>;
  return <DetalheFornecedor key={fornecedor.id} fornecedor={fornecedor} />;
}

function DetalheFornecedor({ fornecedor }: { fornecedor: Fornecedor }) {
  const navegar = useNavigate();
  const invalidar = useInvalidarCadastro();
  const { data: todas } = useFazendas();
  const fazendas = todas?.filter((f) => f.fornecedor_id === fornecedor.id) ?? [];
  const [editando, setEditando] = useState(false);
  const form = useForm<CamposFornecedor>({ defaultValues: camposDeFornecedor(fornecedor) });

  const salvar = useMutation({
    mutationFn: (corpo: unknown) => api.put(`/fornecedores/${fornecedor.id}`, corpo),
    onSuccess: async () => {
      await invalidar();
      setEditando(false);
    },
  });
  const excluir = useMutation({
    mutationFn: () => api.delete(`/fornecedores/${fornecedor.id}`),
    onSuccess: async () => {
      await invalidar();
      navegar("/fornecedores");
    },
  });

  return (
    <>
      <Link to="/fornecedores" className="mb-3 inline-flex items-center gap-1 text-xs text-slate-500 hover:text-slate-950">
        <ArrowLeft size={13} aria-hidden="true" /> Fornecedores
      </Link>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_1fr]">
        <div className="space-y-4">
          <Painel>
            <FaixaTitulo icone={<Users size={13} aria-hidden="true" />}>FORNECEDOR · {fornecedor.tipo_pessoa}</FaixaTitulo>
            <div className="space-y-4 px-5 py-4">
              {editando ? (
                <form onSubmit={form.handleSubmit((c) => salvar.mutate(fornecedorParaApi(c)))} className="space-y-3" noValidate>
                  <CamposCadastraisFornecedor form={form} />
                  <div className="flex gap-2">
                    <Button type="submit" size="sm" disabled={salvar.isPending}>
                      Salvar
                    </Button>
                    <Button type="button" size="sm" variant="outline" onClick={() => setEditando(false)}>
                      Cancelar
                    </Button>
                  </div>
                </form>
              ) : (
                <>
                  <div>
                    <h1 className="text-lg font-semibold text-slate-950">{fornecedor.nome}</h1>
                    <p className="font-mono text-xs text-slate-500">{documento(fornecedor.documento)}</p>
                  </div>
                  <dl className="grid grid-cols-2 gap-x-4 gap-y-3">
                    <Dado rotulo="E-mail">{fornecedor.email ?? "—"}</Dado>
                    <Dado rotulo="Telefone">{fornecedor.telefone ?? "—"}</Dado>
                    <Dado rotulo="Município">{fornecedor.municipio ? `${fornecedor.municipio}${fornecedor.uf ? `/${fornecedor.uf}` : ""}` : "—"}</Dado>
                    <Dado rotulo="Situação">{fornecedor.ativo ? "Ativo" : "Inativo"}</Dado>
                  </dl>
                  <div className="flex flex-wrap gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        form.reset(camposDeFornecedor(fornecedor));
                        setEditando(true);
                      }}
                    >
                      <PenLine aria-hidden="true" /> Editar
                    </Button>
                    <Button
                      size="sm"
                      variant="destructive"
                      disabled={excluir.isPending}
                      onClick={() => {
                        if (window.confirm(`Excluir o fornecedor "${fornecedor.nome}"?`)) excluir.mutate();
                      }}
                    >
                      <Trash2 aria-hidden="true" /> Excluir
                    </Button>
                  </div>
                </>
              )}
              {salvar.error ? <Mensagem>{salvar.error.message}</Mensagem> : null}
              {excluir.error ? <Mensagem>{excluir.error.message}</Mensagem> : null}
            </div>
          </Painel>
          <Painel>
            <Documentos dono="fornecedores" id={fornecedor.id} />
          </Painel>
        </div>

        <Painel className="self-start">
          <FaixaTitulo
            icone={<Sprout size={13} aria-hidden="true" />}
            acoes={
              <Button asChild size="sm" variant="outline">
                <Link to={`/fazendas/nova?fornecedor=${fornecedor.id}`}>
                  <Plus aria-hidden="true" /> Fazenda
                </Link>
              </Button>
            }
          >
            FAZENDAS · {fazendas.length}
          </FaixaTitulo>
          <ul className="divide-y divide-slate-100">
            {fazendas.map((f) => (
              <li key={f.id}>
                <Link to={`/fazendas/${f.id}`} className="flex items-center gap-3 px-5 py-2.5 hover:bg-slate-50">
                  <span className="w-16 shrink-0 font-mono text-[11px] text-slate-500">
                    {f.geometry.type === "Point" ? "ponto" : ha(f.area_declarada_ha, 1).replace(" ha", "")}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm text-slate-950">{f.nome}</span>
                    <span className="block truncate font-mono text-[10px] text-slate-500">{f.car_codigo ?? "CAR não informado"}</span>
                  </span>
                  <StatusPill status={f.status} />
                </Link>
              </li>
            ))}
            {fazendas.length === 0 ? (
              <li className="px-5 py-6 text-center text-sm text-slate-500">Nenhuma fazenda deste fornecedor.</li>
            ) : null}
          </ul>
        </Painel>
      </div>
    </>
  );
}
