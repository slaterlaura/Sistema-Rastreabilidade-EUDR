import type { UseFormReturn } from "react-hook-form";
import { Campo } from "@/components/comum";
import { Input } from "@/components/ui/input";

export interface CamposFazenda {
  nome: string;
  car_codigo: string;
  ccir: string;
  nirf: string;
  matricula: string;
  municipio: string;
  uf: string;
  area_declarada_ha: string;
}

export const camposVazios: CamposFazenda = {
  nome: "",
  car_codigo: "",
  ccir: "",
  nirf: "",
  matricula: "",
  municipio: "",
  uf: "",
  area_declarada_ha: "",
};

/** Converte o formulário para o corpo da API: vazio vira null, UF em maiúsculas, vírgula decimal aceita. */
export function paraApi(c: CamposFazenda) {
  const vazio = (v: string) => (v.trim() === "" ? null : v.trim());
  const area = vazio(c.area_declarada_ha);
  return {
    nome: c.nome.trim(),
    car_codigo: vazio(c.car_codigo),
    ccir: vazio(c.ccir),
    nirf: vazio(c.nirf),
    matricula: vazio(c.matricula),
    municipio: vazio(c.municipio),
    uf: vazio(c.uf)?.toUpperCase() ?? null,
    area_declarada_ha: area === null ? null : Number(area.replace(",", ".")),
  };
}

export function CamposCadastraisFazenda({ form }: { form: UseFormReturn<CamposFazenda> }) {
  const { register, formState } = form;
  const e = formState.errors;
  return (
    <div className="grid grid-cols-2 gap-3">
      <Campo rotulo="Nome da fazenda" erro={e.nome?.message} className="col-span-2">
        <Input {...register("nome", { required: "Informe o nome.", minLength: { value: 2, message: "Nome curto demais." } })} />
      </Campo>
      <Campo rotulo="Código do CAR" className="col-span-2" dica="Ex.: SP-3500105-…">
        <Input className="font-mono text-xs" {...register("car_codigo")} />
      </Campo>
      <Campo rotulo="CCIR">
        <Input {...register("ccir")} />
      </Campo>
      <Campo rotulo="NIRF">
        <Input {...register("nirf")} />
      </Campo>
      <Campo rotulo="Matrícula">
        <Input {...register("matricula")} />
      </Campo>
      <Campo rotulo="Área declarada (ha)" erro={e.area_declarada_ha?.message}>
        <Input
          inputMode="decimal"
          {...register("area_declarada_ha", {
            validate: (v) => v.trim() === "" || Number(v.replace(",", ".")) > 0 || "Informe um número maior que zero.",
          })}
        />
      </Campo>
      <Campo rotulo="Município">
        <Input {...register("municipio")} />
      </Campo>
      <Campo rotulo="UF" erro={e.uf?.message}>
        <Input
          maxLength={2}
          className="uppercase"
          {...register("uf", { validate: (v) => v === "" || /^[A-Za-z]{2}$/.test(v) || "Duas letras." })}
        />
      </Campo>
    </div>
  );
}
