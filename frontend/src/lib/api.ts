/**
 * Cliente da API. Cada chamada é uma execução da Azure Function (cota gratuita do plano Flex),
 * então nada de polling: as telas buscam sob demanda e o React Query reaproveita as respostas.
 */

const BASE = (import.meta.env.VITE_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
const CHAVE_TOKEN = "origemcheck.token";

export class ApiErro extends Error {
  constructor(
    public status: number,
    mensagem: string,
  ) {
    super(mensagem);
  }
}

function lerToken(): string | null {
  try {
    return localStorage.getItem(CHAVE_TOKEN);
  } catch {
    return null;
  }
}

let token: string | null = lerToken();

export function obterToken() {
  return token;
}

export function definirToken(novo: string | null) {
  token = novo;
  try {
    if (novo) localStorage.setItem(CHAVE_TOKEN, novo);
    else localStorage.removeItem(CHAVE_TOKEN);
  } catch {
    // armazenamento indisponível (janela privada): a sessão dura só esta aba
  }
}

/** Disparado quando o servidor recusa o token; o AuthProvider manda para o login. */
export const EVENTO_SESSAO_EXPIRADA = "origemcheck:sessao-expirada";

function mensagemDeErro(corpo: unknown, status: number): string {
  const detalhe = (corpo as { detail?: unknown } | null)?.detail;
  if (typeof detalhe === "string") return detalhe;
  if (Array.isArray(detalhe)) {
    // 422 do FastAPI: lista de campos inválidos
    return detalhe
      .map((d: { loc?: (string | number)[]; msg?: string }) => {
        const campo = d.loc?.filter((p) => p !== "body").join(".");
        return campo ? `${campo}: ${d.msg}` : d.msg;
      })
      .join("; ");
  }
  if (status === 0) return "Não foi possível falar com o servidor. Verifique a conexão.";
  return `Erro ${status} no servidor.`;
}

async function requisitar(caminho: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let resposta: Response;
  try {
    resposta = await fetch(`${BASE}${caminho}`, { ...init, headers });
  } catch {
    throw new ApiErro(0, mensagemDeErro(null, 0));
  }
  if (resposta.status === 401 && token) {
    definirToken(null);
    window.dispatchEvent(new Event(EVENTO_SESSAO_EXPIRADA));
  }
  if (!resposta.ok) {
    const corpo = await resposta.json().catch(() => null);
    throw new ApiErro(resposta.status, mensagemDeErro(corpo, resposta.status));
  }
  return resposta;
}

async function json<T>(caminho: string, init: RequestInit = {}): Promise<T> {
  const resposta = await requisitar(caminho, init);
  if (resposta.status === 204) return undefined as T;
  return resposta.json() as Promise<T>;
}

function comCorpo(metodo: string, corpo: unknown): RequestInit {
  if (corpo instanceof FormData) return { method: metodo, body: corpo };
  return {
    method: metodo,
    body: JSON.stringify(corpo),
    headers: { "Content-Type": "application/json" },
  };
}

function nomeDoArquivo(disposicao: string | null, padrao: string): string {
  if (!disposicao) return padrao;
  const utf8 = /filename\*=UTF-8''([^;]+)/i.exec(disposicao);
  if (utf8) return decodeURIComponent(utf8[1]);
  const simples = /filename="?([^";]+)"?/i.exec(disposicao);
  return simples ? simples[1] : padrao;
}

export const api = {
  get: <T>(caminho: string) => json<T>(caminho),
  post: <T>(caminho: string, corpo?: unknown) => json<T>(caminho, comCorpo("POST", corpo ?? {})),
  put: <T>(caminho: string, corpo: unknown) => json<T>(caminho, comCorpo("PUT", corpo)),
  delete: (caminho: string) => json<void>(caminho, { method: "DELETE" }),

  /** Downloads exigem o token, então não dá para usar um <a href> simples. */
  async baixar(caminho: string, nomePadrao: string) {
    const resposta = await requisitar(caminho);
    const blob = await resposta.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = nomeDoArquivo(resposta.headers.get("Content-Disposition"), nomePadrao);
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  },
};
