import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Download, FileText, Paperclip, Trash2 } from "lucide-react";
import { useRef, useState, type FormEvent } from "react";
import { FaixaTitulo, Mensagem } from "@/components/comum";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { api, ApiErro } from "@/lib/api";
import { chaves, useDocumentos } from "@/lib/consultas";
import { bytes, data } from "@/lib/formato";
import type { TipoDocumento } from "@/lib/tipos";

export const TIPOS_DOCUMENTO: Record<TipoDocumento, string> = {
  car: "CAR",
  ccir: "CCIR",
  matricula: "Matrícula",
  licenca: "Licença",
  contrato: "Contrato",
  outro: "Outro",
};

function vencido(validade: string | null) {
  return validade !== null && validade < new Date().toISOString().slice(0, 10);
}

/** Documentos de um fornecedor ou de uma fazenda: lista, envio, download e exclusão. */
export function Documentos({ dono, id }: { dono: "fornecedores" | "fazendas"; id: number }) {
  const queryClient = useQueryClient();
  const { data: documentos, isLoading } = useDocumentos(dono, id);
  const [tipo, setTipo] = useState<TipoDocumento>("car");
  const [validade, setValidade] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const arquivoRef = useRef<HTMLInputElement>(null);

  const atualizar = () => queryClient.invalidateQueries({ queryKey: chaves.documentos(dono, id) });

  const enviar = useMutation({
    mutationFn: (form: FormData) => api.post(`/${dono}/${id}/documentos`, form),
    onSuccess: () => {
      setErro(null);
      setValidade("");
      if (arquivoRef.current) arquivoRef.current.value = "";
      atualizar();
    },
    onError: (e: Error) => setErro(e.message),
  });

  const excluir = useMutation({
    mutationFn: (docId: number) => api.delete(`/documentos/${docId}`),
    onSuccess: atualizar,
    onError: (e: Error) => setErro(e.message),
  });

  function aoEnviar(e: FormEvent) {
    e.preventDefault();
    const arquivo = arquivoRef.current?.files?.[0];
    if (!arquivo) {
      setErro("Escolha um arquivo PDF, PNG ou JPG.");
      return;
    }
    if (arquivo.size > 10 * 1024 * 1024) {
      setErro("O arquivo passa de 10 MB.");
      return;
    }
    const form = new FormData();
    form.append("arquivo", arquivo);
    form.append("tipo", tipo);
    if (validade) form.append("validade", validade);
    enviar.mutate(form);
  }

  async function baixar(docId: number, nome: string) {
    try {
      await api.baixar(`/documentos/${docId}/arquivo`, nome);
    } catch (e) {
      setErro(e instanceof ApiErro ? e.message : "Não foi possível baixar o arquivo.");
    }
  }

  return (
    <div>
      <FaixaTitulo icone={<Paperclip size={13} aria-hidden="true" />}>DOCUMENTOS</FaixaTitulo>
      <ul className="divide-y divide-slate-100">
        {isLoading ? <li className="px-5 py-4 text-sm text-slate-500">Carregando…</li> : null}
        {documentos?.map((d) => (
          <li key={d.id} className="flex items-center gap-3 px-5 py-2.5">
            <FileText size={16} className="shrink-0 text-slate-400" aria-hidden="true" />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm text-slate-950">
                <span className="mr-1.5 font-mono text-[10px] text-slate-500">{TIPOS_DOCUMENTO[d.tipo].toUpperCase()}</span>
                {d.nome_arquivo}
              </p>
              <p className="truncate font-mono text-[10px] text-slate-500">
                {bytes(d.tamanho_bytes)} · SHA-256 {d.sha256.slice(0, 12)}…
                {d.validade ? (
                  <span className={vencido(d.validade) ? "text-[#a63d2f]" : ""}>
                    {" "}· {vencido(d.validade) ? "VENCIDO EM" : "VALE ATÉ"} {data(d.validade)}
                  </span>
                ) : null}
              </p>
            </div>
            <Button variant="ghost" size="icon" onClick={() => baixar(d.id, d.nome_arquivo)} title="Baixar">
              <Download aria-hidden="true" />
              <span className="sr-only">Baixar {d.nome_arquivo}</span>
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => {
                if (window.confirm(`Excluir o documento "${d.nome_arquivo}"?`)) excluir.mutate(d.id);
              }}
              title="Excluir"
            >
              <Trash2 aria-hidden="true" />
              <span className="sr-only">Excluir {d.nome_arquivo}</span>
            </Button>
          </li>
        ))}
        {documentos?.length === 0 ? (
          <li className="px-5 py-4 text-sm text-slate-500">Nenhum documento anexado. CAR, CCIR e matrícula entram no dossiê.</li>
        ) : null}
      </ul>
      <form onSubmit={aoEnviar} className="space-y-2 border-t border-slate-200 bg-slate-50/60 px-5 py-3">
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-[130px_1fr_150px]">
          <label className="space-y-1">
            <span className="block text-[11px] text-slate-500">Tipo</span>
            <Select value={tipo} onChange={(e) => setTipo(e.target.value as TipoDocumento)}>
              {Object.entries(TIPOS_DOCUMENTO).map(([valor, rotulo]) => (
                <option key={valor} value={valor}>
                  {rotulo}
                </option>
              ))}
            </Select>
          </label>
          <label className="min-w-0 space-y-1">
            <span className="block text-[11px] text-slate-500">Arquivo (PDF, PNG ou JPG, até 10 MB)</span>
            <Input ref={arquivoRef} type="file" accept="application/pdf,image/png,image/jpeg" className="pt-1.5 text-xs" />
          </label>
          <label className="space-y-1">
            <span className="block text-[11px] text-slate-500">Validade (opcional)</span>
            <Input type="date" value={validade} onChange={(e) => setValidade(e.target.value)} />
          </label>
        </div>
        {erro ? <Mensagem>{erro}</Mensagem> : null}
        <Button type="submit" size="sm" variant="outline" disabled={enviar.isPending}>
          <Paperclip aria-hidden="true" /> {enviar.isPending ? "Enviando…" : "Anexar documento"}
        </Button>
      </form>
    </div>
  );
}
