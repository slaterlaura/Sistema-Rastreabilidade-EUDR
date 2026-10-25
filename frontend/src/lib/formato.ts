const numero = (casas: number) =>
  new Intl.NumberFormat("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });

/** Hectare é a unidade do produtor: a interface nunca mostra m². */
export function ha(valorHa: number | string | null | undefined, casas = 2): string {
  if (valorHa === null || valorHa === undefined || valorHa === "") return "—";
  return `${numero(casas).format(Number(valorHa))} ha`;
}

export function haDeM2(m2: number | string | null | undefined, casas?: number): string {
  if (m2 === null || m2 === undefined) return "—";
  const valor = Number(m2) / 10_000;
  // sobreposições de borda são pequenas: sem casas extras viraria "0,00 ha"
  return ha(valor, casas ?? (valor > 0 && valor < 1 ? 4 : 2));
}

export function kg(valor: number | string | null | undefined): string {
  if (valor === null || valor === undefined) return "—";
  return `${numero(0).format(Number(valor))} kg`;
}

export function data(iso: string | null | undefined): string {
  if (!iso) return "—";
  const [ano, mes, dia] = iso.slice(0, 10).split("-");
  return `${dia}/${mes}/${ano}`;
}

export function dataHora(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

export function documento(digitos: string): string {
  if (digitos.length === 11) return digitos.replace(/(\d{3})(\d{3})(\d{3})(\d{2})/, "$1.$2.$3-$4");
  if (digitos.length === 14) return digitos.replace(/(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})/, "$1.$2.$3/$4-$5");
  return digitos;
}

export function bytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${numero(0).format(n / 1024)} KB`;
  return `${numero(1).format(n / 1024 / 1024)} MB`;
}
