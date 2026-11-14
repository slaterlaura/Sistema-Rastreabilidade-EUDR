# OrigemCheck — Sistema de Rastreabilidade de Origem (EUDR)

Cadastro de fornecedores e fazendas, verificação automática de desmatamento pós-2020 (PRODES)
e dossiê de origem por embarque. O contexto completo e as regras de negócio estão em [context.md](context.md).

- **Vai contribuir?** Leia o [CONTRIBUTING.md](CONTRIBUTING.md): toda mudança passa por PR, testes automáticos e aprovação; o deploy no Azure é automático no merge.
- **Como o sistema funciona:** [docs/COMO-FUNCIONA.md](docs/COMO-FUNCIONA.md). **Deploy e infraestrutura:** [docs/DEPLOY-AZURE.md](docs/DEPLOY-AZURE.md). **Banco de dados:** [docs/BANCO-DE-DADOS.md](docs/BANCO-DE-DADOS.md).

## Acesse o sistema

| | Link |
|---|---|
| **Site** | https://kind-pebble-04924410f.3.azurestaticapps.net |
| **API (FastAPI): documentação interativa** | https://func-origemcheck-lslater26.azurewebsites.net/docs |
| API: saúde do serviço e do banco | https://func-origemcheck-lslater26.azurewebsites.net/health/db |

**Login de demonstração:** `demo@exemplo.com.br` / `demo-origemcheck-2026`

A primeira chamada depois de um tempo parado pode levar alguns segundos (a API "acorda").

Telas: quadro de fazendas (lista com filtros + mapa com a supressão do PRODES hachurada), cadastro com desenho
de polígono ou ponto, fornecedores com documentos, composição de embarque (fazendas recusadas visíveis, com o motivo),
evidências e dossiês congelados.

Para rodar na sua máquina (banco local, backend e frontend), siga o [CONTRIBUTING.md](CONTRIBUTING.md), seção 1.

## Mais dados de desmatamento (PRODES)

Baixe o "Incremento anual de desmatamento" do bioma no TerraBrasilis e salve em `data/raw/` (fora do git).
**Não precisa converter para GeoJSON**: o script lê o `.zip` ou o `.shp` direto e recorta pela UF e pelos anos
posteriores a 2020 já na leitura.

```bash
cd backend
# bioma inteiro (só DESMATAMENTO e anos > 2020)
python scripts/carga_prodes.py --arquivo ../data/raw/yearly_deforestation_biome_cerrado_v20261016.zip --bioma Cerrado
# só uma UF (aceita sigla; o arquivo pode trazer "MG" ou "MINAS GERAIS")
python scripts/carga_prodes.py --arquivo ../data/raw/yearly_deforestation.zip --bioma Cerrado --uf MG
# zip com duas camadas (Amazônia)
python scripts/carga_prodes.py --arquivo ../data/raw/prodes_amazonia_legal_2026_pri_v20261016.zip \
    --camada yearly_deforestation_2026_pri_amazonia_legal_v20261015 --bioma "Amazonia preliminar"
# só gerar o GeoJSON recortado, sem mexer no banco:
python scripts/carga_prodes.py --arquivo ../data/raw/yearly_deforestation.zip --uf MG --somente-converter ../data/raw/prodes_cerrado_mg.geojson
```

Depois, no app: **Fazendas → Reprocessar camada**. Opções: `python scripts/carga_prodes.py --help`.

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

## Links úteis

- **Bases dos biomas (PRODES, TerraBrasilis):** https://terrabrasilis.dpi.inpe.br/geonetwork/srv/eng/catalog.search#/metadata/2b439f5a-b53d-4d56-9937-99026a205e9e
- **Base dos imóveis rurais (consulta pública do CAR):** https://consultapublica.car.gov.br/publico/imoveis/index
- **Conversor de formatos geográficos (Mapshaper):** https://mapshaper.org/ — útil para inspecionar ou simplificar arquivos;
  para carregar o PRODES não é preciso converter (o `carga_prodes.py` lê o `.zip` direto).
