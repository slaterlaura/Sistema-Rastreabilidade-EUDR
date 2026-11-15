/**
 * Campo de texto com lista de sugestões (setas para navegar, Enter para escolher, Esc para fechar).
 * O texto continua livre: as sugestões ajudam, não obrigam.
 */

import { forwardRef, useId, useState, type InputHTMLAttributes, type ReactNode } from "react";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

export interface Sugestao<T> {
  chave: string;
  rotulo: ReactNode;
  detalhe?: ReactNode;
  valor: T;
}

interface Props<T> extends Omit<InputHTMLAttributes<HTMLInputElement>, "value" | "onChange"> {
  valor: string;
  onValor: (texto: string) => void;
  sugestoes: Sugestao<T>[];
  onEscolher: (item: T) => void;
  /** Mostrado no fim da lista quando não há sugestão (ex.: "Nenhum município encontrado"). */
  vazio?: ReactNode;
  classeLista?: string;
}

function AutocompletarBase<T>(
  { valor, onValor, sugestoes, onEscolher, vazio, className, classeLista, onKeyDown, onBlur, onFocus, ...resto }: Props<T>,
  ref: React.ForwardedRef<HTMLInputElement>,
) {
  const id = useId();
  const [aberta, setAberta] = useState(false);
  const [ativa, setAtiva] = useState(0);
  const mostrar = aberta && valor.trim().length > 0 && (sugestoes.length > 0 || vazio);

  function escolher(item: Sugestao<T>) {
    onEscolher(item.valor);
    setAberta(false);
  }

  return (
    <div className="relative">
      <Input
        ref={ref}
        role="combobox"
        aria-expanded={Boolean(mostrar)}
        aria-controls={`${id}-lista`}
        aria-autocomplete="list"
        autoComplete="off"
        value={valor}
        className={className}
        onChange={(e) => {
          onValor(e.target.value);
          setAberta(true);
          setAtiva(0);
        }}
        onFocus={(e) => {
          setAberta(true);
          onFocus?.(e);
        }}
        onBlur={(e) => {
          // espera o clique na sugestão antes de fechar
          window.setTimeout(() => setAberta(false), 200);
          onBlur?.(e);
        }}
        onKeyDown={(e) => {
          if (mostrar && sugestoes.length > 0) {
            if (e.key === "ArrowDown") {
              e.preventDefault();
              setAtiva((i) => (i + 1) % sugestoes.length);
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setAtiva((i) => (i - 1 + sugestoes.length) % sugestoes.length);
            } else if (e.key === "Enter") {
              e.preventDefault();
              escolher(sugestoes[Math.min(ativa, sugestoes.length - 1)]);
            }
          }
          if (e.key === "Escape") setAberta(false);
          onKeyDown?.(e);
        }}
        {...resto}
      />
      {mostrar ? (
        <ul
          id={`${id}-lista`}
          role="listbox"
          className={cn(
            "absolute top-full right-0 left-0 z-[1100] mt-1 max-h-64 overflow-y-auto rounded-lg border border-slate-200 bg-white py-1 text-sm shadow-lg",
            classeLista,
          )}
        >
          {sugestoes.map((s, i) => (
            <li
              key={s.chave}
              role="option"
              aria-selected={i === ativa}
              onMouseDown={(e) => e.preventDefault()}
              onMouseEnter={() => setAtiva(i)}
              onClick={() => escolher(s)}
              className={cn(
                "flex cursor-pointer items-baseline justify-between gap-3 px-3 py-1.5",
                i === ativa ? "bg-slate-100 text-slate-950" : "text-slate-700",
              )}
            >
              <span className="min-w-0 truncate">{s.rotulo}</span>
              {s.detalhe ? <span className="shrink-0 font-mono text-[10px] text-slate-500">{s.detalhe}</span> : null}
            </li>
          ))}
          {sugestoes.length === 0 && vazio ? <li className="px-3 py-1.5 text-xs text-slate-500">{vazio}</li> : null}
        </ul>
      ) : null}
    </div>
  );
}

export const Autocompletar = forwardRef(AutocompletarBase) as <T>(
  props: Props<T> & { ref?: React.ForwardedRef<HTMLInputElement> },
) => ReturnType<typeof AutocompletarBase>;
