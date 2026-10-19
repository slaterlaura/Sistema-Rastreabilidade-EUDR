import { FileUp, Plus, RefreshCw } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { CabecalhoPagina, Carregando, Mensagem, Painel, FaixaTitulo } from "@/components/comum";
import { Button } from "@/components/ui/button";
import FazendasBoard from "@/components/ui/fazendas-board";
import { Input, Select } from "@/components/ui/input";
import { api } from "@/lib/api";
import { useFazendas, useFornecedores, useInvalidarCadastro, useReverificarTodas } from "@/lib/consultas";
import { STATUS } from "@/lib/status";

export default function PaginaFazendas() {
  const { data: fazendas, isLoading, error } = useFazendas();
  const { data: fornecedores } = useFornecedores();
  const [importando, setImportando] = useState(false);
  const reverificar = useReverificarTodas();

  const bloqueadas = fazendas?.filter((f) => f.status === "bloqueada").length ?? 0;

  return (
    <>
      <CabecalhoPagina
        titulo="Fazendas"
        subtitulo={
          fazendas ? (
            <>
              {fazendas.length} fazenda(s) ·{" "}
              <span style={{ color: bloqueadas ? STATUS.bloqueada.cor : undefined }}>{bloqueadas} bloqueada(s)</span> por
              supressão posterior a 31/12/2020
            </>
          ) : undefined
        }
        acoes={
          <>
            <Button
              variant="ghost"
              size="sm"
              disabled={reverificar.isPending || !fazendas?.length}
              onClick={() => {
                if (window.confirm("Reprocessar todas as fazendas contra a camada PRODES atual? Use quando a camada for atualizada.")) {
                  reverificar.mutate();
                }
              }}
            >
              <RefreshCw className={reverificar.isPending ? "animate-spin" : ""} aria-hidden="true" /> Reprocessar camada
            </Button>
            <Button variant="outline" size="sm" onClick={() => setImportando((v) => !v)} aria-expanded={importando}>
              <FileUp aria-hidden="true" /> Importar GeoJSON
            </Button>
            <Button asChild size="sm">
              <Link to="/fazendas/nova">
                <Plus aria-hidden="true" /> Nova fazenda
              </Link>
            </Button>
          </>
        }
      />

      {reverificar.data ? (
        <div className="mb-4">
          <Mensagem tipo={reverificar.data.mudaram_de_status.length ? "aviso" : "sucesso"}>
            {reverificar.data.verificadas} fazenda(s) reverificada(s).{" "}
            {reverificar.data.mudaram_de_status.length
              ? `Mudaram de status: ${reverificar.data.mudaram_de_status.map((m) => `${m.nome} (${m.de} → ${m.para})`).join(", ")}.`
              : "Nenhuma mudou de status."}
          </Mensagem>
        </div>
      ) : null}
      {reverificar.error ? (
        <div className="mb-4">
          <Mensagem>{reverificar.error.message}</Mensagem>
        </div>
      ) : null}

      {importando ? <ImportarGeoJSON aoTerminar={() => setImportando(false)} /> : null}

      {error ? <Mensagem>{error.message}</Mensagem> : null}
      {isLoading ? (
        <Carregando />
      ) : fazendas ? (
        <FazendasBoard fazendas={fazendas} fornecedores={fornecedores} className="h-[calc(100dvh-190px)] min-h-[560px]" />
      ) : null}
    </>
  );
}

function ImportarGeoJSON({ aoTerminar }: { aoTerminar: () => void }) {
  const { data: fornecedores } = useFornecedores();
  const invalidar = useInvalidarCadastro();
  const [fornecedorId, setFornecedorId] = useState("");
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function enviar(e: FormEvent) {
    e.preventDefault();
    setErro(null);
    if (!fornecedorId || !arquivo) {
      setErro("Escolha o fornecedor e o arquivo.");
      return;
    }
    let geojson: unknown;
    try {
      geojson = JSON.parse(await arquivo.text());
    } catch {
      setErro("O arquivo não é um JSON válido.");
      return;
    }
    setEnviando(true);
    try {
      const r = await api.post<{ importadas: number; resumo: { apta: number; bloqueada: number } }>("/fazendas/import-geojson", {
        fornecedor_id: Number(fornecedorId),
        geojson,
      });
      await invalidar();
      window.alert(`${r.importadas} fazenda(s) importada(s): ${r.resumo.apta} apta(s), ${r.resumo.bloqueada} bloqueada(s).`);
      aoTerminar();
    } catch (e) {
      setErro((e as Error).message);
    } finally {
      setEnviando(false);
    }
  }

  return (
    <Painel className="mb-4">
      <FaixaTitulo icone={<FileUp size={13} aria-hidden="true" />}>IMPORTAR GEOJSON</FaixaTitulo>
      <form onSubmit={enviar} className="space-y-3 px-5 py-4">
        <p className="text-xs text-slate-600">
          Um FeatureCollection com polígonos (por exemplo, o recorte do SICAR). As propriedades <code className="font-mono">cod_imovel</code>,{" "}
          <code className="font-mono">municipio</code> e <code className="font-mono">num_area</code> viram CAR, município e área
          declarada. A importação é tudo ou nada: se uma feição for inválida, nenhuma é gravada.
        </p>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-[260px_1fr_auto] sm:items-end">
          <label className="space-y-1">
            <span className="block text-xs font-medium text-slate-600">Fornecedor</span>
            <Select value={fornecedorId} onChange={(e) => setFornecedorId(e.target.value)}>
              <option value="">Escolha…</option>
              {fornecedores?.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.nome}
                </option>
              ))}
            </Select>
          </label>
          <label className="min-w-0 space-y-1">
            <span className="block text-xs font-medium text-slate-600">Arquivo .geojson ou .json</span>
            <Input type="file" accept=".geojson,.json,application/geo+json,application/json" className="pt-1.5 text-xs" onChange={(e) => setArquivo(e.target.files?.[0] ?? null)} />
          </label>
          <Button type="submit" disabled={enviando}>
            {enviando ? "Importando…" : "Importar e verificar"}
          </Button>
        </div>
        {erro ? <Mensagem>{erro}</Mensagem> : null}
      </form>
    </Painel>
  );
}
