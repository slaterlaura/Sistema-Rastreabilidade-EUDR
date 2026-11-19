"""Produtos que um embarque pode declarar (EUDR, anexo I: café = posição SH 0901).

A chave é o que se grava no banco; a descrição e o código SH vão para a tela, o retrato e o PDF.
O frontend tem a mesma lista em frontend/src/lib/produtos.ts: ao mudar aqui, mude lá.
"""

PRODUTOS: dict[str, tuple[str, str]] = {
    "cafe_arabica_verde": ("Café arábica verde (cru, em grão)", "0901.11"),
    "cafe_conilon_verde": ("Café conilon/robusta verde (cru, em grão)", "0901.11"),
    "cafe_blend_verde": ("Café verde, blend arábica e conilon", "0901.11"),
    "cafe_verde_descafeinado": ("Café verde descafeinado", "0901.12"),
    "cafe_torrado_grao": ("Café torrado em grão", "0901.21"),
}


def descrever(produto: str | None) -> dict | None:
    """Produto como vai para a saída da API e para o dossiê."""
    if produto is None:
        return None
    descricao, codigo_sh = PRODUTOS.get(produto, (produto, None))
    return {"codigo": produto, "descricao": descricao, "codigo_sh": codigo_sh}
