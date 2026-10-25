import { ArrowLeft, Download, FileCheck2, Lock } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Carregando, Dado, FaixaTitulo, Mensagem, Painel, StatusPill } from "@/components/comum";
import { TIPOS_DOCUMENTO } from "@/components/documentos";
import { Button } from "@/components/ui/button";
import { AjustarTamanho, DefinicoesHachura, Enquadrar, GeometriaFazendaMapa, LegendaMapa, Mapa } from "@/components/ui/fazendas-board-utils/mapa";
import { api } from "@/lib/api";
import { useDossie } from "@/lib/consultas";
import { data, dataHora, documento, ha, haDeM2, kg } from "@/lib/formato";

export default function PaginaDossie() {
  const id = Number(useParams().id);
  const { data: dossie, isLoading, error } = useDossie(id);
  const [erro, setErro] = useState<string | null>(null);
  if (isLoading) return <Carregando />;
  if (error || !dossie?.retrato) return <Mensagem>{error?.message ?? "Dossiê não encontrado."}</Mensagem>;
  const r = dossie.retrato;

  const baixar = async (formato: "geojson" | "pdf") => {
    setErro(null);
    try {
      await api.baixar(`/dossies/${dossie.id}/${formato}`, `dossie-${r.embarque.identificacao}.${formato}`);
    } catch (e) {
      setErro((e as Error).message);
    }
  };

  return (
    <>
      <Link to="/dossies" className="mb-3 inline-flex items-center gap-1 text-xs text-slate-500 hover:text-slate-950">
        <ArrowLeft size={13} aria-hidden="true" /> Dossiês
      </Link>
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="font-mono text-xl font-semibold tracking-tight text-slate-950">{r.embarque.identificacao}</h1>
          <p className="mt-1 flex items-center gap-1.5 text-sm text-slate-500">
            <Lock size={13} aria-hidden="true" /> Retrato congelado em {dataHora(r.gerado_em)}. Mudanças posteriores no cadastro ou no
            PRODES não alteram este dossiê.
          </p>
        </div>
        <div className="flex gap-2">
          <Button onClick={() => baixar("geojson")}>
            <Download aria-hidden="true" /> GeoJSON
          </Button>
          <Button variant="outline" onClick={() => baixar("pdf")}>
            <Download aria-hidden="true" /> PDF
          </Button>
        </div>
      </div>
      {erro ? (
        <div className="mb-3">
          <Mensagem>{erro}</Mensagem>
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_1fr]">
        <div className="space-y-4">
          <Painel>
            <FaixaTitulo icone={<FileCheck2 size={13} aria-hidden="true" />}>EMBARQUE</FaixaTitulo>
            <dl className="grid grid-cols-2 gap-4 px-5 py-4 sm:grid-cols-3">
              <Dado rotulo="Destino">{r.embarque.destino}</Dado>
              <Dado rotulo="Data do embarque">{data(r.embarque.data_embarque)}</Dado>
              <Dado rotulo="Total">{kg(r.total_kg)}</Dado>
              <Dado rotulo="Exportador">{r.exportador.nome}</Dado>
              <Dado rotulo="Data de corte">{data(r.criterios.data_corte_desmatamento)}</Dado>
              <Dado rotulo="Tolerância">{haDeM2(r.criterios.tolerancia_m2, 1)}</Dado>
            </dl>
            <div className="space-y-1 border-t border-slate-100 px-5 py-3">
              {r.camadas_referencia.map((c) => (
                <p key={c.id} className="font-mono text-[10px] text-slate-500">
                  CAMADA #{c.id} · {c.origem} {c.bioma}
                  {c.uf ? `/${c.uf}` : ""} · {c.n_feicoes} FEIÇÕES · CARREGADA {dataHora(c.carregada_em)}
                </p>
              ))}
            </div>
          </Painel>

          <Painel>
            <FaixaTitulo>PARCELAS · {r.parcelas.length}</FaixaTitulo>
            <ul className="divide-y divide-slate-100">
              {r.parcelas.map((p) => (
                <li key={p.parcela_id} className="space-y-1.5 px-5 py-3">
                  <div className="flex items-center gap-3">
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium text-slate-950">{p.fazenda.nome}</span>
                      <span className="block truncate text-xs text-slate-500">
                        {p.fornecedor.nome} · {documento(p.fornecedor.documento)}
                      </span>
                    </span>
                    <span className="shrink-0 font-mono text-xs text-slate-950">{kg(p.quantidade_kg)}</span>
                    <StatusPill status={p.fazenda.status} />
                  </div>
                  <p className="font-mono text-[10px] text-slate-500">
                    CAR {p.fazenda.car_codigo ?? "—"} · {p.fazenda.geometry.type === "Point" ? "PONTO" : "POLÍGONO"} ·{" "}
                    {ha(p.fazenda.area_declarada_ha)} · VERIFICADA {dataHora(p.fazenda.verificada_em)}
                  </p>
                  {[...p.fazenda.documentos, ...p.fornecedor.documentos].map((d) => (
                    <p key={d.id} className="truncate font-mono text-[10px] text-slate-500">
                      {TIPOS_DOCUMENTO[d.tipo].toUpperCase()} · {d.nome_arquivo} · SHA-256 {d.sha256.slice(0, 16)}…
                    </p>
                  ))}
                </li>
              ))}
            </ul>
          </Painel>
        </div>

        <div className="relative min-h-[420px] overflow-hidden rounded-2xl border border-slate-200 bg-white lg:sticky lg:top-20 lg:h-[calc(100dvh-160px)]">
          <DefinicoesHachura />
          <Mapa>
            <AjustarTamanho />
            <Enquadrar geometrias={r.parcelas.map((p) => p.fazenda.geometry)} chave={String(dossie.id)} />
            {/* Geometrias e status do retrato, não do cadastro atual */}
            {r.parcelas.map((p) => (
              <GeometriaFazendaMapa key={p.parcela_id} geometria={p.fazenda.geometry} status={p.fazenda.status} rotulo={p.fazenda.nome} />
            ))}
          </Mapa>
          <div className="pointer-events-none absolute bottom-6 left-3 z-[500] hidden sm:block">
            <LegendaMapa comSupressao={false} />
          </div>
        </div>
      </div>
    </>
  );
}
