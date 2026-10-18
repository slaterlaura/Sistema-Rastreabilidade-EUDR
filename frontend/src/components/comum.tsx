import { AlertTriangle, CheckCircle2, Loader2 } from "lucide-react";
import type { ReactNode } from "react";
import { STATUS } from "@/lib/status";
import type { StatusFazenda } from "@/lib/tipos";
import { cn } from "@/lib/utils";

export function Painel({ className, children }: { className?: string; children: ReactNode }) {
  return <section className={cn("overflow-hidden rounded-2xl border border-slate-200 bg-white", className)}>{children}</section>;
}

/** Faixa de título no estilo do quadro: ícone + rótulo em mono, espaçado. */
export function FaixaTitulo({ icone, children, acoes }: { icone?: ReactNode; children: ReactNode; acoes?: ReactNode }) {
  return (
    <div className="flex min-h-11 items-center justify-between gap-3 border-b border-slate-200 bg-slate-50 px-5 py-2">
      <p className="flex items-center gap-2 font-mono text-[10px] tracking-widest text-slate-500">
        {icone}
        {children}
      </p>
      {acoes ? <div className="flex items-center gap-1.5">{acoes}</div> : null}
    </div>
  );
}

export function CabecalhoPagina({ titulo, subtitulo, acoes }: { titulo: string; subtitulo?: ReactNode; acoes?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        <h1 className="truncate text-xl font-semibold tracking-tight text-slate-950">{titulo}</h1>
        {subtitulo ? <p className="mt-1 text-sm text-slate-500">{subtitulo}</p> : null}
      </div>
      {acoes ? <div className="flex flex-wrap gap-2">{acoes}</div> : null}
    </div>
  );
}

export function StatusPill({ status, className }: { status: StatusFazenda; className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-1.5", className)}>
      <span aria-hidden="true" className="size-1.5 rounded-full" style={{ backgroundColor: STATUS[status].cor }} />
      <span className="font-mono text-[10px] text-slate-600">{STATUS[status].rotulo.toUpperCase()}</span>
    </span>
  );
}

export function Mensagem({ tipo = "erro", children }: { tipo?: "erro" | "sucesso" | "aviso"; children: ReactNode }) {
  const estilos = {
    erro: "border-red-200 bg-red-50 text-red-900",
    sucesso: "border-green-200 bg-green-50 text-green-900",
    aviso: "border-amber-200 bg-amber-50 text-amber-900",
  };
  const Icone = tipo === "sucesso" ? CheckCircle2 : AlertTriangle;
  return (
    <div role={tipo === "erro" ? "alert" : "status"} className={cn("flex gap-2 rounded-lg border px-3 py-2 text-sm", estilos[tipo])}>
      <Icone size={16} className="mt-0.5 shrink-0" aria-hidden="true" />
      <div className="min-w-0">{children}</div>
    </div>
  );
}

export function Carregando({ texto = "Carregando…" }: { texto?: string }) {
  return (
    <p className="flex items-center justify-center gap-2 py-10 text-sm text-slate-500">
      <Loader2 size={16} className="animate-spin" aria-hidden="true" /> {texto}
    </p>
  );
}

export function Campo({ rotulo, erro, children, className, dica }: { rotulo: string; erro?: string; children: ReactNode; className?: string; dica?: string }) {
  return (
    <label className={cn("block space-y-1", className)}>
      <span className="block text-xs font-medium text-slate-600">{rotulo}</span>
      {children}
      {erro ? <span className="block text-xs text-red-700">{erro}</span> : dica ? <span className="block text-xs text-slate-500">{dica}</span> : null}
    </label>
  );
}

export function Dado({ rotulo, children, mono }: { rotulo: string; children: ReactNode; mono?: boolean }) {
  return (
    <div className="min-w-0">
      <dt className="font-mono text-[10px] tracking-wide text-slate-500">{rotulo.toUpperCase()}</dt>
      <dd className={cn("truncate text-sm text-slate-950", mono && "font-mono text-xs")}>{children}</dd>
    </div>
  );
}
