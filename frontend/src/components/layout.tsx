import { FileCheck2, LogOut, Ship, Sprout, Users } from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";
import { useSessao } from "@/lib/auth";
import { cn } from "@/lib/utils";

const NAVEGACAO = [
  { para: "/fazendas", rotulo: "Fazendas", icone: Sprout },
  { para: "/fornecedores", rotulo: "Fornecedores", icone: Users },
  { para: "/embarques", rotulo: "Embarques", icone: Ship },
  { para: "/dossies", rotulo: "Dossiês", icone: FileCheck2 },
];

export function Layout() {
  const { usuario, sair } = useSessao();
  return (
    <div className="min-h-dvh bg-slate-100/70">
      <header className="sticky top-0 z-[1000] border-b border-slate-200 bg-white/95 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-[1400px] items-center gap-4 px-4 sm:px-6">
          <NavLink to="/fazendas" className="flex shrink-0 items-center gap-2">
            <span className="flex size-7 items-center justify-center rounded-lg bg-slate-950 text-white">
              <Sprout size={15} aria-hidden="true" />
            </span>
            <span className="hidden font-mono text-[11px] font-medium tracking-widest text-slate-950 sm:inline">ORIGEMCHECK</span>
          </NavLink>
          <nav aria-label="Principal" className="-mx-1 flex min-w-0 flex-1 gap-1 overflow-x-auto px-1">
            {NAVEGACAO.map(({ para, rotulo, icone: Icone }) => (
              <NavLink
                key={para}
                to={para}
                title={rotulo}
                className={({ isActive }) =>
                  cn(
                    "flex shrink-0 items-center gap-1.5 rounded-full px-3 py-1.5 text-[13px] font-medium",
                    isActive ? "bg-slate-950 text-white" : "text-slate-600 hover:bg-slate-100 hover:text-slate-950",
                  )
                }
              >
                <Icone size={14} aria-hidden="true" />
                <span className="sr-only sm:not-sr-only">{rotulo}</span>
              </NavLink>
            ))}
          </nav>
          <div className="flex shrink-0 items-center gap-2">
            <span className="hidden max-w-40 truncate text-xs text-slate-500 md:inline">{usuario?.nome}</span>
            <button
              type="button"
              onClick={sair}
              className="flex items-center gap-1.5 rounded-full px-2.5 py-1.5 text-xs text-slate-600 hover:bg-slate-100 hover:text-slate-950"
            >
              <LogOut size={14} aria-hidden="true" />
              <span className="hidden sm:inline">Sair</span>
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-[1400px] px-4 py-6 sm:px-6">
        <Outlet />
      </main>
    </div>
  );
}
