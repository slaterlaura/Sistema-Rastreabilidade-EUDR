import type { UseFormReturn } from "react-hook-form";
import { Campo } from "@/components/comum";
import { Input, Select } from "@/components/ui/input";
import { BEBIDAS, PENEIRAS, PRODUTOS, REGIOES, TIPOS } from "@/lib/produtos";
import type { Embarque } from "@/lib/tipos";

/** Campos do formulário de embarque (criar e editar). Vazio = "" no formulário, null na API. */
export interface CamposEmbarque {
  identificacao: string;
  data_embarque: string;
  destino: string;
  produto: string;
  tipo_classificacao: string;
  bebida: string;
  peneira: string;
  regiao_origem: string;
}

export const embarqueVazio: CamposEmbarque = {
  identificacao: "",
  data_embarque: "",
  destino: "",
  produto: "",
  tipo_classificacao: "",
  bebida: "",
  peneira: "",
  regiao_origem: "",
};

export function embarqueParaCampos(e: Embarque): CamposEmbarque {
  return {
    identificacao: e.identificacao,
    data_embarque: e.data_embarque,
    destino: e.destino,
    produto: e.produto?.codigo ?? "",
    tipo_classificacao: e.tipo_classificacao ?? "",
    bebida: e.bebida ?? "",
    peneira: e.peneira ?? "",
    regiao_origem: e.regiao_origem ?? "",
  };
}

export function embarqueParaApi(c: CamposEmbarque) {
  const ou = (v: string) => v.trim() || null;
  return {
    identificacao: c.identificacao.trim(),
    data_embarque: c.data_embarque,
    destino: c.destino.trim(),
    produto: ou(c.produto),
    tipo_classificacao: ou(c.tipo_classificacao),
    bebida: ou(c.bebida),
    peneira: ou(c.peneira),
    regiao_origem: ou(c.regiao_origem),
  };
}

/** Lista de opções que mantém visível um valor salvo fora dela (ex.: digitado por outra via). */
function comValorAtual(opcoes: string[], atual: string) {
  return atual && !opcoes.includes(atual) ? [atual, ...opcoes] : opcoes;
}

export function CamposDoEmbarque({ form }: { form: UseFormReturn<CamposEmbarque> }) {
  const erros = form.formState.errors;
  const bebidaAtual = form.watch("bebida");
  const bebidasConhecidas = BEBIDAS.flatMap((g) => g.opcoes);
  return (
    <div className="space-y-3">
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

      <Campo rotulo="Produto" erro={erros.produto?.message} dica="Obrigatório para fechar o embarque. O código SH vai para o dossiê.">
        <Select {...form.register("produto", { required: "Escolha o produto." })}>
          <option value="">Escolha o produto…</option>
          {PRODUTOS.map((p) => (
            <option key={p.codigo} value={p.codigo}>
              {p.descricao} · SH {p.codigo_sh}
            </option>
          ))}
        </Select>
      </Campo>

      <fieldset className="space-y-2">
        <legend className="text-xs font-medium text-slate-600">
          Especificação de qualidade do lote <span className="font-normal text-slate-500">(vale para todas as parcelas)</span>
        </legend>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-4">
          <Campo rotulo="Tipo (COB/NY)">
            <Select {...form.register("tipo_classificacao")}>
              <option value="">—</option>
              {comValorAtual(TIPOS, form.watch("tipo_classificacao")).map((t) => (
                <option key={t}>{t}</option>
              ))}
            </Select>
          </Campo>
          <Campo rotulo="Bebida">
            <Select {...form.register("bebida")}>
              <option value="">—</option>
              {bebidaAtual && !bebidasConhecidas.includes(bebidaAtual) ? <option>{bebidaAtual}</option> : null}
              {BEBIDAS.map((g) => (
                <optgroup key={g.grupo} label={g.grupo}>
                  {g.opcoes.map((b) => (
                    <option key={b}>{b}</option>
                  ))}
                </optgroup>
              ))}
            </Select>
          </Campo>
          <Campo rotulo="Peneira">
            <Select {...form.register("peneira")}>
              <option value="">—</option>
              {comValorAtual(PENEIRAS, form.watch("peneira")).map((p) => (
                <option key={p}>{p}</option>
              ))}
            </Select>
          </Campo>
          <Campo rotulo="Região de origem">
            <Input list="regioes-cafe" placeholder="Ex.: Cerrado Mineiro" {...form.register("regiao_origem")} />
            <datalist id="regioes-cafe">
              {REGIOES.map((r) => (
                <option key={r} value={r} />
              ))}
            </datalist>
          </Campo>
        </div>
      </fieldset>
    </div>
  );
}
