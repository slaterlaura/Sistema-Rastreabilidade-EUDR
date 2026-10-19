import { ChevronRight, Download, FileCheck2 } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { CabecalhoPagina, Carregando, FaixaTitulo, Mensagem, Painel } from "@/components/comum";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { useDossies } from "@/lib/consultas";
import { data, dataHora, kg } from "@/lib/formato";

export default function PaginaDossies() {
  const { data: dossies, isLoading, error } = useDossies();
  const [erro, setErro] = useState<string | null>(null);
  const baixar = async (id: number, identificacao: string, formato: "geojson" | "pdf") => {
    setErro(null);
    try {
      await api.baixar(`/dossies/${id}/${formato}`, `dossie-${identificacao}.${formato}`);
    } catch (e) {
      setErro((e as Error).message);
    }
  };
  return (
    <>
      <CabecalhoPagina
        titulo="Dossiês"
        subtitulo="Visão de auditoria: cada dossiê é o retrato do que se sabia no fechamento do embarque e nunca muda."
      />
      {error ? <Mensagem>{error.message}</Mensagem> : null}
      {erro ? (
        <div className="mb-3">
          <Mensagem>{erro}</Mensagem>
        </div>
      ) : null}
      <Painel>
        <FaixaTitulo icone={<FileCheck2 size={13} aria-hidden="true" />}>DOSSIÊS</FaixaTitulo>
        {isLoading ? <Carregando /> : null}
        <ul className="divide-y divide-slate-100">
          {dossies?.map((d) => (
            <li key={d.id} className="flex items-center gap-4 px-5 py-3">
              <span className="w-20 shrink-0 font-mono text-[11px] text-slate-500">{data(d.data_embarque)}</span>
              <Link to={`/dossies/${d.id}`} className="group min-w-0 flex-1">
                <span className="block truncate font-mono text-sm font-medium text-slate-950 group-hover:underline">{d.embarque_identificacao}</span>
                <span className="block truncate text-xs text-slate-500">
                  {d.destino} · {d.n_parcelas} parcela(s) · {kg(d.total_kg)} · gerado {dataHora(d.gerado_em)}
                </span>
              </Link>
              <div className="hidden shrink-0 gap-1 sm:flex">
                <Button size="sm" variant="outline" onClick={() => baixar(d.id, d.embarque_identificacao, "geojson")}>
                  <Download aria-hidden="true" /> GeoJSON
                </Button>
                <Button size="sm" variant="ghost" onClick={() => baixar(d.id, d.embarque_identificacao, "pdf")}>
                  <Download aria-hidden="true" /> PDF
                </Button>
              </div>
              <Link to={`/dossies/${d.id}`} aria-label={`Abrir dossiê ${d.embarque_identificacao}`}>
                <ChevronRight size={16} className="text-slate-400" aria-hidden="true" />
              </Link>
            </li>
          ))}
          {dossies?.length === 0 ? (
            <li className="px-5 py-8 text-center text-sm text-slate-500">Nenhum dossiê ainda. Eles nascem ao fechar um embarque.</li>
          ) : null}
        </ul>
      </Painel>
    </>
  );
}
