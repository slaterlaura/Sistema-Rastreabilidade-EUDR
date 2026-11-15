import { Campo } from "@/components/comum";
import { Autocompletar } from "@/components/ui/autocompletar";
import { Select } from "@/components/ui/input";
import { buscarMunicipios, UFS, useLocalidades, type Municipio } from "@/lib/localidades";

/**
 * Município com sugestões (filtradas pela UF, se escolhida) e UF em lista.
 * Escolher um município preenche a UF dele; o município continua podendo ser digitado livremente.
 */
export function CamposMunicipioUf({
  municipio,
  uf,
  onMunicipio,
  onUf,
  classeMunicipio,
  classeUf,
}: {
  municipio: string;
  uf: string;
  onMunicipio: (v: string) => void;
  onUf: (v: string) => void;
  classeMunicipio?: string;
  classeUf?: string;
}) {
  const { data, isError } = useLocalidades();
  const sugestoes = data ? buscarMunicipios(data.municipios, municipio, uf || undefined) : [];
  const siglaAtual = uf.toUpperCase();
  const ufConhecida = siglaAtual === "" || UFS.some((u) => u.sigla === siglaAtual);

  return (
    <>
      <Campo rotulo="Município" className={classeMunicipio} dica={isError ? "Sugestões indisponíveis; digite o nome." : undefined}>
        <Autocompletar<Municipio>
          valor={municipio}
          onValor={onMunicipio}
          sugestoes={sugestoes.map((m) => ({ chave: `${m.uf}-${m.nome}`, rotulo: m.nome, detalhe: m.uf, valor: m }))}
          onEscolher={(m) => {
            onMunicipio(m.nome);
            onUf(m.uf);
          }}
          vazio={data && municipio.trim().length >= 2 ? `Nenhum município${uf ? ` em ${siglaAtual}` : ""} com esse nome.` : undefined}
          placeholder={uf ? `Município de ${siglaAtual}…` : "Comece a digitar…"}
        />
      </Campo>
      <Campo rotulo="UF" className={classeUf}>
        <Select value={siglaAtual} onChange={(e) => onUf(e.target.value)}>
          <option value="">—</option>
          {/* valor antigo fora da lista (cadastro anterior) continua visível */}
          {!ufConhecida ? <option value={siglaAtual}>{siglaAtual}</option> : null}
          {UFS.map((u) => (
            <option key={u.sigla} value={u.sigla}>
              {u.sigla} · {u.nome}
            </option>
          ))}
        </Select>
      </Campo>
    </>
  );
}
