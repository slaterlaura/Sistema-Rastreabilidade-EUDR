import type { UseFormReturn } from "react-hook-form";
import { CamposMunicipioUf } from "@/components/campos-localidade";
import { Campo } from "@/components/comum";
import { Input } from "@/components/ui/input";
import type { Fornecedor } from "@/lib/tipos";

export interface CamposFornecedor {
  nome: string;
  documento: string;
  email: string;
  telefone: string;
  municipio: string;
  uf: string;
}

export const fornecedorVazio: CamposFornecedor = { nome: "", documento: "", email: "", telefone: "", municipio: "", uf: "" };

export function camposDeFornecedor(f: Fornecedor): CamposFornecedor {
  return {
    nome: f.nome,
    documento: f.documento,
    email: f.email ?? "",
    telefone: f.telefone ?? "",
    municipio: f.municipio ?? "",
    uf: f.uf ?? "",
  };
}

export function fornecedorParaApi(c: CamposFornecedor) {
  const vazio = (v: string) => (v.trim() === "" ? null : v.trim());
  return {
    nome: c.nome.trim(),
    documento: c.documento,
    email: vazio(c.email),
    telefone: vazio(c.telefone),
    municipio: vazio(c.municipio),
    uf: vazio(c.uf)?.toUpperCase() ?? null,
  };
}

export function CamposCadastraisFornecedor({ form }: { form: UseFormReturn<CamposFornecedor> }) {
  const { register, formState, watch, setValue } = form;
  const e = formState.errors;
  const marcar = { shouldDirty: true };
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-6">
      <Campo rotulo="Nome ou razão social" erro={e.nome?.message} className="sm:col-span-4">
        <Input {...register("nome", { required: "Informe o nome." })} />
      </Campo>
      <Campo rotulo="CPF ou CNPJ" erro={e.documento?.message} className="sm:col-span-2">
        <Input
          inputMode="numeric"
          className="font-mono text-xs"
          {...register("documento", {
            required: "Informe o CPF ou CNPJ.",
            validate: (v) => [11, 14].includes(v.replace(/\D/g, "").length) || "CPF tem 11 dígitos; CNPJ tem 14.",
          })}
        />
      </Campo>
      <Campo rotulo="E-mail" className="sm:col-span-3">
        <Input type="email" {...register("email")} />
      </Campo>
      <Campo rotulo="Telefone" className="sm:col-span-3">
        <Input type="tel" {...register("telefone")} />
      </Campo>
      <CamposMunicipioUf
        municipio={watch("municipio")}
        uf={watch("uf")}
        onMunicipio={(v) => setValue("municipio", v, marcar)}
        onUf={(v) => setValue("uf", v, marcar)}
        classeMunicipio="sm:col-span-4"
        classeUf="sm:col-span-2"
      />
    </div>
  );
}
