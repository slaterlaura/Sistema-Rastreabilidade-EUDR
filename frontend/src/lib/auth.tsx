import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, definirToken, EVENTO_SESSAO_EXPIRADA, obterToken } from "@/lib/api";
import type { Usuario } from "@/lib/tipos";

interface Sessao {
  autenticado: boolean;
  usuario: Usuario | undefined;
  entrar: (email: string, senha: string) => Promise<void>;
  registrar: (nome: string, email: string, senha: string) => Promise<void>;
  sair: () => void;
}

const ContextoSessao = createContext<Sessao | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState(obterToken());
  const queryClient = useQueryClient();

  const { data: usuario } = useQuery({
    queryKey: ["eu", token],
    queryFn: () => api.get<Usuario>("/auth/eu"),
    enabled: Boolean(token),
    staleTime: Infinity,
  });

  const sair = useCallback(() => {
    definirToken(null);
    setToken(null);
    queryClient.clear();
  }, [queryClient]);

  useEffect(() => {
    const aoExpirar = () => sair();
    window.addEventListener(EVENTO_SESSAO_EXPIRADA, aoExpirar);
    return () => window.removeEventListener(EVENTO_SESSAO_EXPIRADA, aoExpirar);
  }, [sair]);

  const entrar = useCallback(async (email: string, senha: string) => {
    const { access_token } = await api.post<{ access_token: string }>("/auth/login", { email, senha });
    definirToken(access_token);
    setToken(access_token);
  }, []);

  const registrar = useCallback(
    async (nome: string, email: string, senha: string) => {
      await api.post("/auth/registrar", { nome, email, senha });
      await entrar(email, senha);
    },
    [entrar],
  );

  const valor = useMemo(
    () => ({ autenticado: Boolean(token), usuario, entrar, registrar, sair }),
    [token, usuario, entrar, registrar, sair],
  );
  return <ContextoSessao.Provider value={valor}>{children}</ContextoSessao.Provider>;
}

export function useSessao() {
  const sessao = useContext(ContextoSessao);
  if (!sessao) throw new Error("useSessao fora do AuthProvider");
  return sessao;
}
