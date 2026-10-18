# OrigemCheck — Sistema de Rastreabilidade de Origem (EUDR)

Cadastro de fornecedores e fazendas, verificação automática de desmatamento pós-2020 (PRODES)
e dossiê de origem por embarque. O contexto completo e as regras de negócio estão em [context.md](context.md).

## Como rodar (backend)

```bash
cp .env.example .env                      # ajuste as senhas; DATABASE_URL usa a mesma senha do Postgres
docker compose up -d                      # PostgreSQL 16 + PostGIS na porta 5433

cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

alembic upgrade head                      # cria o schema (única fonte: migrações Alembic)
python scripts/carga_prodes.py --arquivo ../data/processed/MataAtlantica_desmatamento_SP.json \
    --bioma "Mata Atlantica" --uf SP      # carrega a camada de supressão
python scripts/seed.py                    # opcional: dados de demonstração
uvicorn app.main:app --reload             # http://localhost:8000/docs
```

Login da demonstração: `demo@exemplo.com.br` / `demo-origemcheck-2026`.

## Testes

```bash
cd backend && python -m pytest tests -q
```

Os testes criam e recriam um banco próprio (`eudr_test`) no mesmo servidor do `.env`; não tocam no banco de desenvolvimento.

## Fluxo

1. `POST /auth/registrar` e `POST /auth/login` → token (`Authorization: Bearer ...`).
2. Cadastre o fornecedor e as fazendas (`POST /fornecedores`, `POST /fazendas` ou `POST /fazendas/import-geojson`).
   Cada fazenda é verificada ao salvar e recebe o status `apta` ou `bloqueada`.
3. Anexe documentos (CAR, CCIR, matrícula, licenças) em `/fornecedores/{id}/documentos` e `/fazendas/{id}/documentos`.
4. Crie o embarque e defina as parcelas (`PUT /embarques/{id}/parcelas`). Fazendas bloqueadas são recusadas com 400.
5. `POST /embarques/{id}/fechar` congela os dados e gera o dossiê; baixe em `/dossies/{id}/geojson` e `/dossies/{id}/pdf`.

## Configuração

| Variável | Para que serve | Padrão |
|---|---|---|
| `DATABASE_URL` | Conexão com o PostgreSQL | obrigatória |
| `JWT_SECRET` | Chave de assinatura dos tokens | **troque em produção** |
| `TOLERANCIA_M2` | Sobreposição abaixo disso não bloqueia (R5) | 1000 |
| `CORS_ORIGENS` | Origens permitidas, separadas por vírgula | `http://localhost:5173` |
| `STORAGE_DIR` | Pasta dos documentos e dossiês | `backend/storage` |

## Banco

O schema é criado **somente** pelas migrações (`backend/alembic`). Não altere tabelas direto no banco.
Para uma nova migração: `alembic revision --autogenerate -m "descrição"` e confira o arquivo gerado.
