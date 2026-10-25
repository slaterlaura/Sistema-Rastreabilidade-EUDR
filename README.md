# OrigemCheck — Sistema de Rastreabilidade de Origem (EUDR)

Cadastro de fornecedores e fazendas, verificação automática de desmatamento pós-2020 (PRODES)
e dossiê de origem por embarque. O contexto completo e as regras de negócio estão em [context.md](context.md).

## Como rodar (backend)

```bash
cp .env.example .env                      # ajuste as senhas; DATABASE_URL usa a mesma senha do Postgres
docker compose up -d                      # PostgreSQL 16 + PostGIS na porta 5433

cd backend
python3.13 -m venv .venv && source .venv/bin/activate   # Python 3.13: o mesmo do Azure Functions
pip install -r requirements-dev.txt

alembic upgrade head                      # cria o schema (única fonte: migrações Alembic)
python scripts/carga_prodes.py --arquivo ../data/processed/MataAtlantica_desmatamento_SP.json \
    --bioma "Mata Atlantica" --uf SP      # carrega a camada de supressão
python scripts/seed.py                    # opcional: dados de demonstração
uvicorn app.main:app --reload             # http://localhost:8000/docs
```

Login da demonstração: `demo@exemplo.com.br` / `demo-origemcheck-2026`.

## Como rodar (frontend)

```bash
cd frontend
cp .env.example .env          # VITE_API_URL=http://localhost:8000 (ou a URL da Function)
npm install
npm run dev                   # http://localhost:5173
npm run build                 # typecheck + build de produção em dist/ (vai para o Static Web Apps)
```

Telas: quadro de fazendas (lista com filtros + mapa com a supressão do PRODES hachurada), cadastro com desenho
de polígono ou ponto, fornecedores com documentos, composição de embarque (fazendas recusadas visíveis, com o motivo),
evidências e dossiês congelados.

## Testes

```bash
cd backend && python -m pytest tests -q
```

Os testes criam e recriam um banco próprio (`eudr_test`) no mesmo servidor do `.env`; não tocam no banco de desenvolvimento.

## Hospedagem: Azure Functions

O backend roda no **Azure Functions (plano Flex Consumption, Python 3.13)**: `backend/function_app.py` embrulha o
mesmo FastAPI do `uvicorn` (rotas idênticas, sem prefixo `/api`). Escolhido para ficar na cota gratuita; cada
requisição HTTP conta como uma execução, então evite monitores de uptime e *polling*.

- **Arquivos** (documentos e dossiês) vão para o **Blob Storage** em produção (`STORAGE_BACKEND=blob`); em dev ficam em disco.
- **Provisionar:** `infra/azure-functions.sh` (comandos `az` comentados; revise antes de rodar).
- **Publicar:** workflow `.github/workflows/backend.yml` (testes + deploy) ou `func azure functionapp publish <app> --python` em `backend/`.
- **Migrações e cargas** rodam da sua máquina com `DATABASE_URL` apontando para o Azure, não dentro da Function.
- **Testar o empacotamento local:** instale o Azure Functions Core Tools, copie `backend/local.settings.sample.json` para
  `backend/local.settings.json` e rode `func start` em `backend/` (porta 7071).

Detalhes, limites de conexão, CORS e custo: [context.md](context.md), seção 12.

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
| `STORAGE_BACKEND` | `local` (disco) ou `blob` (Azure Blob Storage) | `local` |
| `STORAGE_DIR` | Pasta dos arquivos quando `local` | `backend/storage` |
| `BLOB_ACCOUNT_URL` | `https://<conta>.blob.core.windows.net` (identidade gerenciada) | — |
| `BLOB_CONNECTION_STRING` | Só para Azurite/dev | — |
| `BLOB_CONTAINER` | Contêiner dos arquivos | `origemcheck-arquivos` |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | Pool por instância da Function | 3 / 2 |

## Banco

O schema é criado **somente** pelas migrações (`backend/alembic`). Não altere tabelas direto no banco.
Para uma nova migração: `alembic revision --autogenerate -m "descrição"` e confira o arquivo gerado.
