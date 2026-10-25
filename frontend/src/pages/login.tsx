import { Sprout } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Navigate } from "react-router-dom";
import { Campo, Mensagem } from "@/components/comum";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useSessao } from "@/lib/auth";

interface Formulario {
  nome: string;
  email: string;
  senha: string;
}

export default function PaginaLogin() {
  const { autenticado, entrar, registrar } = useSessao();
  const [modo, setModo] = useState<"entrar" | "registrar">("entrar");
  const [erro, setErro] = useState<string | null>(null);
  const { register, handleSubmit, formState } = useForm<Formulario>();

  if (autenticado) return <Navigate to="/fazendas" replace />;

  const enviar = handleSubmit(async ({ nome, email, senha }) => {
    setErro(null);
    try {
      if (modo === "entrar") await entrar(email, senha);
      else await registrar(nome, email, senha);
    } catch (e) {
      setErro((e as Error).message);
    }
  });

  return (
    <div className="flex min-h-dvh items-center justify-center bg-slate-100/70 px-4">
      <div className="w-full max-w-sm overflow-hidden rounded-2xl border border-slate-200 bg-white">
        <div className="border-b border-slate-200 bg-slate-50 px-6 py-4">
          <p className="flex items-center gap-2 font-mono text-[10px] tracking-widest text-slate-500">
            <Sprout size={13} aria-hidden="true" /> ORIGEMCHECK · EUDR
          </p>
          <h1 className="mt-2 text-lg font-semibold text-slate-950">
            {modo === "entrar" ? "Entrar na sua conta" : "Criar conta do exportador"}
          </h1>
        </div>
        <form onSubmit={enviar} className="space-y-3 px-6 py-5" noValidate>
          {modo === "registrar" ? (
            <Campo rotulo="Nome" erro={formState.errors.nome?.message}>
              <Input autoComplete="name" {...register("nome", { required: "Informe seu nome." })} />
            </Campo>
          ) : null}
          <Campo rotulo="E-mail" erro={formState.errors.email?.message}>
            <Input type="email" autoComplete="email" {...register("email", { required: "Informe o e-mail." })} />
          </Campo>
          <Campo rotulo="Senha" erro={formState.errors.senha?.message} dica={modo === "registrar" ? "Mínimo de 8 caracteres." : undefined}>
            <Input
              type="password"
              autoComplete={modo === "entrar" ? "current-password" : "new-password"}
              {...register("senha", {
                required: "Informe a senha.",
                minLength: modo === "registrar" ? { value: 8, message: "Mínimo de 8 caracteres." } : undefined,
              })}
            />
          </Campo>
          {erro ? <Mensagem>{erro}</Mensagem> : null}
          <Button type="submit" className="w-full" disabled={formState.isSubmitting}>
            {formState.isSubmitting ? "Aguarde…" : modo === "entrar" ? "Entrar" : "Criar conta"}
          </Button>
          <button
            type="button"
            onClick={() => {
              setErro(null);
              setModo(modo === "entrar" ? "registrar" : "entrar");
            }}
            className="w-full text-center text-xs text-slate-500 hover:text-slate-950"
          >
            {modo === "entrar" ? "Não tem conta? Criar uma" : "Já tem conta? Entrar"}
          </button>
        </form>
      </div>
    </div>
  );
}
