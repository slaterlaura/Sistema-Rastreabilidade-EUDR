/**
 * Quadro de fazendas: a lista com filtros por status à esquerda e o mapa à direita,
 * no mesmo desenho do "departures board" (chips, rótulos em fonte mono, linha selecionada em laranja).
 *
 * Em vez de rotas de voo, o mapa mostra as fazendas com a cor do traço pelo status
 * e a supressão do PRODES hachurada por baixo.
 */

import { ArrowRight, Layers, MapPin, Sprout } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { Link } from "react-router-dom";
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
import { dataHora, ha, haDeM2 } from "@/lib/formato";
import { STATUS } from "@/lib/status";
import type { Fazenda, Fornecedor, StatusFazenda } from "@/lib/tipos";
import { cn } from "@/lib/utils";

type Filtro = "todas" | StatusFazenda;
const FILTROS: { valor: Filtro; rotulo: string }[] = [
  { valor: "todas", rotulo: "Todas" },
  { valor: "apta", rotulo: "Aptas" },
  { valor: "bloqueada", rotulo: "Bloqueadas" },
  { valor: "pendente", rotulo: "Pendentes" },
];

export interface FazendasBoardProps {
  fazendas: readonly Fazenda[];
  fornecedores?: readonly Fornecedor[];
  selecionadaInicial?: number | null;
  className?: string;
}

function areaExibida(f: Fazenda): string {
  if (f.geometry.type === "Point") return f.area_declarada_ha ? ha(f.area_declarada_ha, 1) : "ponto";
  return f.area_declarada_ha ? ha(f.area_declarada_ha, 1) : "—";
}

function FazendasBoard({ fazendas, fornecedores = [], selecionadaInicial = null, className }: FazendasBoardProps) {
  const [filtro, setFiltro] = useState<Filtro>("todas");
  const [selecionada, setSelecionada] = useState<number | null>(selecionadaInicial);
  const [supressaoVisivel, setSupressaoVisivel] = useState(true);
  const [estadoCamada, setEstadoCamada] = useState<EstadoCamada | null>(null);
  const aoMudarCamada = useCallback((e: EstadoCamada) => setEstadoCamada(e), []);

  const nomeFornecedor = useMemo(() => new Map(fornecedores.map((f) => [f.id, f.nome])), [fornecedores]);
  const contagem = useMemo(() => {
    const c: Record<Filtro, number> = { todas: fazendas.length, apta: 0, bloqueada: 0, pendente: 0 };
    for (const f of fazendas) c[f.status] += 1;
    return c;
  }, [fazendas]);

  const visiveis = fazendas.filter((f) => filtro === "todas" || f.status === filtro);
  const fazendaSelecionada = visiveis.find((f) => f.id === selecionada) ?? null;
  // Selecionada por último, para ficar por cima das outras no mapa
  const ordemMapa = fazendaSelecionada
    ? [...visiveis.filter((f) => f.id !== fazendaSelecionada.id), fazendaSelecionada]
    : visiveis;

  return (
    <div
      className={cn(
        "grid min-h-[520px] w-full min-w-0 grid-cols-1 overflow-hidden rounded-2xl border border-slate-200 bg-white lg:grid-cols-[360px_1fr]",
        className,
      )}
    >
      <aside className="flex min-h-0 flex-col border-b border-slate-200 lg:border-r lg:border-b-0">
        <div className="border-b border-slate-200 bg-slate-50 px-5 py-3">
          <p className="flex items-center gap-2 font-mono text-[10px] tracking-widest text-slate-500">
            <Sprout size={13} aria-hidden="true" /> FAZENDAS
          </p>
        </div>
        <div role="group" aria-label="Filtrar por status" className="flex flex-wrap gap-1.5 border-b border-slate-200 p-3">
          {FILTROS.map(({ valor, rotulo }) => (
            <button
              key={valor}
              type="button"
              onClick={() => setFiltro(valor)}
              aria-pressed={filtro === valor}
              className={cn(
                "flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium",
                filtro === valor
                  ? "border-slate-950 bg-slate-950 text-white"
                  : "border-slate-200 text-slate-600 hover:text-slate-950",
              )}
            >
              {valor !== "todas" ? (
                <span aria-hidden="true" className="size-1.5 rounded-full" style={{ backgroundColor: STATUS[valor].cor }} />
              ) : null}
              {rotulo}
              <span className={cn("font-mono text-[10px]", filtro === valor ? "text-slate-300" : "text-slate-400")}>
                {contagem[valor]}
              </span>
            </button>
          ))}
        </div>
        <ul aria-label="Lista de fazendas" className="max-h-72 min-h-0 flex-1 overflow-y-auto p-2 lg:max-h-none">
          {visiveis.map((f) => {
            const ativa = selecionada === f.id;
            const local = [f.municipio, f.uf].filter(Boolean).join("/");
            return (
              <li key={f.id}>
                <button
                  type="button"
                  onClick={() => setSelecionada(ativa ? null : f.id)}
                  aria-pressed={ativa}
                  className={cn(
                    "flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left hover:bg-slate-100",
                    ativa && "bg-orange-50 hover:bg-orange-50",
                  )}
                >
                  <span className="w-14 shrink-0 font-mono text-[11px] text-slate-500">
                    {f.geometry.type === "Point" ? (
                      <span className="inline-flex items-center gap-1">
                        <MapPin size={11} aria-hidden="true" />
                        {f.area_declarada_ha ? ha(f.area_declarada_ha, 1).replace(" ha", "") : "—"}
                      </span>
                    ) : (
                      areaExibida(f).replace(" ha", "")
                    )}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className={cn("block truncate text-sm font-medium", ativa ? "text-orange-800" : "text-slate-950")}>
                      {f.nome}
                    </span>
                    <span className="block truncate text-xs text-slate-500">
                      {nomeFornecedor.get(f.fornecedor_id) ?? "—"}
                      {local ? ` · ${local}` : ""}
                    </span>
                  </span>
                  <span className="flex shrink-0 items-center gap-1.5">
                    <span aria-hidden="true" className="size-1.5 rounded-full" style={{ backgroundColor: STATUS[f.status].cor }} />
                    <span className="font-mono text-[10px] text-slate-500">{STATUS[f.status].rotulo.toUpperCase()}</span>
                  </span>
                </button>
              </li>
            );
          })}
          {visiveis.length === 0 ? (
            <li className="px-3 py-6 text-center text-sm text-slate-500">
              {fazendas.length === 0
                ? "Nenhuma fazenda cadastrada ainda."
                : `Nenhuma fazenda ${FILTROS.find((x) => x.valor === filtro)?.rotulo.toLowerCase()} no momento.`}
            </li>
          ) : null}
        </ul>
        <p className="border-t border-slate-200 px-4 py-3 font-mono text-[10px] text-slate-500">
          {visiveis.length} DE {fazendas.length} FAZENDAS · ÁREA EM HECTARES
        </p>
      </aside>

      <div className="relative min-h-[380px]">
        <DefinicoesHachura />
        <Mapa>
          <AjustarTamanho />
          <Enquadrar geometrias={fazendas.map((f) => f.geometry)} chave={String(fazendas.length)} />
          <CamadaSupressao visivel={supressaoVisivel} onEstado={aoMudarCamada} />
          {ordemMapa.map((f) => (
            <GeometriaFazendaMapa
              key={f.id}
              geometria={f.geometry}
              status={f.status}
              rotulo={f.nome}
              selecionada={f.id === fazendaSelecionada?.id}
              esmaecida={fazendaSelecionada !== null && f.id !== fazendaSelecionada.id}
              onClick={() => setSelecionada(f.id)}
            />
          ))}
        </Mapa>

        <div className="pointer-events-none absolute top-3 right-16 left-14 z-[500] flex flex-wrap items-start gap-2">
          <button
            type="button"
            onClick={() => setSupressaoVisivel((v) => !v)}
            aria-pressed={supressaoVisivel}
            className={cn(
              "pointer-events-auto flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium shadow-sm",
              supressaoVisivel ? "border-slate-950 bg-slate-950 text-white" : "border-slate-200 bg-white text-slate-600",
            )}
          >
            <Layers size={12} aria-hidden="true" /> Supressão PRODES
          </button>
          <AvisoCamada estado={estadoCamada} visivel={supressaoVisivel} />
        </div>
        <div className="pointer-events-none absolute bottom-6 left-3 z-[500] hidden sm:block">
          <LegendaMapa comSupressao={supressaoVisivel} />
        </div>

        {fazendaSelecionada ? <CartaoFazenda fazenda={fazendaSelecionada} fornecedor={nomeFornecedor.get(fazendaSelecionada.fornecedor_id)} /> : null}
      </div>
    </div>
  );
}

function CartaoFazenda({ fazenda, fornecedor }: { fazenda: Fazenda; fornecedor?: string }) {
  const estilo = STATUS[fazenda.status];
  const sobreposicao = Number(fazenda.area_sobreposta_m2);
  return (
    <div className="absolute right-3 bottom-6 z-[500] w-[min(320px,calc(100%-24px))] rounded-xl border border-slate-200 bg-white p-4 shadow-lg">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-slate-950">{fazenda.nome}</p>
          <p className="truncate text-xs text-slate-500">{fornecedor ?? "—"}</p>
        </div>
        <span
          className="shrink-0 rounded-full px-2 py-0.5 font-mono text-[10px] font-medium text-white"
          style={{ backgroundColor: estilo.cor }}
        >
          {estilo.rotulo.toUpperCase()}
        </span>
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-2 text-xs">
        <div>
          <dt className="font-mono text-[10px] text-slate-500">SOBREPOSIÇÃO</dt>
          <dd className={cn("font-medium", sobreposicao > 0 ? "text-[#a63d2f]" : "text-slate-950")}>
            {fazenda.geometry.type === "Point"
              ? fazenda.status === "bloqueada"
                ? "ponto dentro"
                : "ponto fora"
              : haDeM2(sobreposicao)}
          </dd>
        </div>
        <div>
          <dt className="font-mono text-[10px] text-slate-500">ÁREA DECLARADA</dt>
          <dd className="font-medium text-slate-950">{ha(fazenda.area_declarada_ha)}</dd>
        </div>
        <div className="col-span-2">
          <dt className="font-mono text-[10px] text-slate-500">CAR</dt>
          <dd className="truncate font-mono text-[11px] text-slate-950">{fazenda.car_codigo ?? "não informado"}</dd>
        </div>
        <div className="col-span-2">
          <dt className="font-mono text-[10px] text-slate-500">VERIFICADA EM</dt>
          <dd className="text-slate-950">{dataHora(fazenda.verificada_em)}</dd>
        </div>
      </dl>
      <Link
        to={`/fazendas/${fazenda.id}`}
        className="mt-3 flex items-center justify-center gap-1.5 rounded-lg border border-slate-200 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 hover:text-slate-950"
      >
        Abrir fazenda <ArrowRight size={13} aria-hidden="true" />
      </Link>
    </div>
  );
}

export default FazendasBoard;
