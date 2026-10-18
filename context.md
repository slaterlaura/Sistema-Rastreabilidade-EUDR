# OrigemCheck — Sistema de Rastreabilidade de Origem (EUDR)

Contexto do projeto para assistentes de código. Leia por inteiro antes de gerar código.
Idioma do código e da interface: **português do Brasil**. Comentários e identificadores em português.

---

## 1. O que é

Sistema web que permite a **exportadores de café de médio porte** registrar as áreas produtivas
de seus fornecedores, verificar automaticamente se há desmatamento posterior a 31/12/2020
nessas áreas, e gerar um pacote de evidências de origem para cada embarque destinado à
União Europeia.

### Por que existe

O Regulamento (UE) 2023/1115 (EUDR) passa a ser aplicável em **30/12/2026** para operadores
de grande e médio porte, e em 30/06/2027 para micro e pequenas empresas. A data de corte de
desmatamento é **31/12/2020** e não mudou em nenhum dos adiamentos.

A obrigação legal é do **importador europeu**, não do produtor brasileiro. O importador precisa,
por remessa: geolocalização de cada fazenda de origem, evidência de ausência de desmatamento
pós-2020, e evidência de legalidade. Ele repassa essa exigência contratualmente ao exportador.
Hoje o exportador médio resolve isso em planilha e e-mail.

O Brasil é classificado como **risco padrão**, portanto não cabe o procedimento simplificado.

---

## 2. Regras de negócio invariantes

Estas regras definem a corretude do sistema. Não as altere sem instrução explícita.

### R1 — A verificação é automática, nunca manual

A checagem espacial roda como efeito de salvar ou alterar a geometria de uma fazenda.
Não existe tela "verificar". Existe apenas um endpoint de reprocessamento manual, para quando
a camada de referência for atualizada.

Uma fazenda nunca pode ficar no estado "cadastrada mas não verificada" de forma silenciosa.

### R2 — O bloqueio é validado no servidor

Fazenda com `status = 'bloqueada'` não pode compor embarque. A validação é no backend e
retorna 400 nomeando as fazendas recusadas. Esconder o botão na interface não é a regra —
é apenas a cortesia visual que a acompanha.

### R3 — O dossiê é um retrato congelado

Ao fechar um embarque, o sistema **copia** para dentro do dossiê os dados daquele instante:
geometrias, CAR, status, área sobreposta, data da verificação, versão da camada de referência,
quantidades das parcelas e os documentos anexados (com o SHA-256 de cada arquivo).
Não guarda apenas chaves estrangeiras.

Motivo: se o PRODES for atualizado depois e uma fazenda passar a bloqueada, o dossiê de abril
não pode mudar retroativamente. Ele é a evidência do que se sabia na época. Referência viva
destruiria a prova em vez de preservá-la.

Implementação: coluna `JSONB` em `dossie` com o retrato completo, mais os arquivos em storage.

### R4 — Ponto para fazendas de até 4 hectares

O regulamento admite ponto único para fazendas de até 4 ha e exige polígono acima disso.

Consequências:
- A coluna geométrica é `GEOMETRY(Geometry, 4326)`, nunca `GEOMETRY(Polygon, 4326)`.
- Validação: ponto só é aceito se a área declarada for ≤ 4 ha.
- Na checagem, um ponto não tem área: `ST_Area` da interseção sempre retorna 0.
  O critério vira binário (cai ou não cai dentro do polígono de supressão) e a tolerância
  em m² **não se aplica**. Tratar esse caso explicitamente, senão toda fazenda em ponto
  sai apta silenciosamente.

### R5 — Tolerância de sobreposição

Sobreposição abaixo de `TOLERANCIA_M2` (padrão: 1000 m²) não bloqueia. Sobreposições de poucos
metros quase sempre são imprecisão de digitalização de borda. O valor é configurável por
variável de ambiente e deve ser documentado.

Não se aplica a geometrias em ponto (ver R4).

### R6 — Multi-tenant simples

Um exportador por conta. Toda consulta filtra por `usuario_id`. Sem perfis, sem papéis,
sem organização. Se um recurso não pertence ao usuário logado, retorna 404, não 403.

---

## 3. Escopo

### Dentro

1. Autenticação simples (JWT, um usuário por exportador)
2. CRUD de fornecedores, com campos cadastrais completos
3. CRUD de fazendas (um fornecedor tem várias) com geometria — desenho no mapa ou importação de GeoJSON
   e anexos de documentos (CAR, CCIR, matrícula, licenças, contratos) por fornecedor e por fazenda
4. Checagem espacial automática contra PRODES Cerrado
5. Embarques compostos por parcelas (quantidade de cada fazenda), com bloqueio das fazendas não conformes
6. Geração de dossiê: GeoJSON + PDF
7. Listagem de dossiês (visão de auditoria)
8. Deploy em Azure

### Fora — não implementar sem instrução

- **Lotes, mistura de cargas e balanço de massa.** É o ponto mais difícil do problema real
  (café de vários produtores se junta em armazém), deliberadamente cortado.
- Camadas adicionais: embargos do Ibama, terras indígenas, unidades de conservação
- Portal de acesso para o importador
- Trilha de auditoria completa e perfis de acesso
- Jobs agendados, filas, Terraform
- **Qualquer componente de IA ou OCR.** Explicitamente fora do escopo principal.

---

## 4. Personas

| Persona | Papel | O que decorre disso |
|---|---|---|
| **Mariana**, analista de comércio exterior | Usuária primária. ~15 embarques/mês. Sem formação em GIS. | A interface é otimizada para ela. Inserir geometria não pode pressupor conhecimento de SIG. |
| **Roberto**, sócio-diretor | Consulta, não opera. Usa celular. | O status precisa ser legível em dois segundos, por cor, não só em relatório. |
| **Klaus**, analista de conformidade do importador | Não usa o sistema. Lê a evidência. | O GeoJSON tem prioridade sobre o PDF: é processável por sistema. |

O produtor rural **não** é usuário nesta versão. A geometria chega pelo exportador.

---

## 5. Stack

| Camada | Tecnologia |
|---|---|
| Frontend | React 18 + Vite, React-Leaflet, leaflet-draw, React Query, React Hook Form |
| Backend | FastAPI, SQLAlchemy 2.x, GeoAlchemy2, Pydantic v2, Alembic |
| Banco | PostgreSQL 16 + PostGIS 3.4 |
| Geoprocessamento | Shapely, GeoPandas (só na carga) |
| PDF | ReportLab |
| Deploy | Docker; Azure App Service for Containers + Azure Database for PostgreSQL Flexible Server + Azure Static Web Apps |

Restrição: **crédito Azure for Students de USD 100**. Dimensionar para Burstable B1ms e
App Service B1. Não provisionar armazenamento "por garantia".

---

## 6. Estrutura do repositório

Monorepo.

```
rastreabilidade-eudr/
├─ backend/
│  ├─ app/
│  │  ├─ main.py            # inicialização do FastAPI, CORS, routers
│  │  ├─ config.py          # pydantic-settings, lê o .env (tolerância, JWT, storage)
│  │  ├─ database.py        # engine, SessionLocal, get_db
│  │  ├─ models.py          # tabelas SQLAlchemy
│  │  ├─ schemas.py         # modelos Pydantic
│  │  ├─ auth.py            # JWT e hash de senha (bcrypt)
│  │  ├─ routers/           # um arquivo por recurso
│  │  │  ├─ auth.py  fornecedores.py  fazendas.py  documentos.py  embarques.py  dossies.py
│  │  └─ services/
│  │     ├─ geometria.py    # validação e normalização do GeoJSON recebido
│  │     ├─ verificacao.py  # checagem espacial (R1, R4, R5)
│  │     ├─ dossie.py       # retrato congelado, GeoJSON e PDF
│  │     └─ arquivos.py     # storage (disco no dev; Azure Blob no deploy)
│  ├─ alembic/              # migrações (única fonte do schema)
│  ├─ scripts/
│  │  ├─ init/01-postgis.sql
│  │  ├─ carga_prodes.py    # carrega a camada PRODES (cria uma versão)
│  │  └─ seed.py            # dados de demonstração
│  ├─ tests/
│  ├─ requirements.txt
│  └─ Dockerfile
├─ frontend/
│  └─ src/
│     ├─ pages/  components/  api.js
├─ docker-compose.yml
├─ .env.example
└─ README.md
```

---

## 7. Modelo de dados

```
usuario ──< fornecedor ──< fazenda ──< parcela >── embarque ──< dossie
                │             │
                └──< documento >┘     (documento pertence a um fornecedor OU a uma fazenda)

camada_versao ──< camada_prodes       (independente; a fazenda guarda a versão que a verificou)
```

**Vocabulário.** *Fazenda* é a área produtiva com geometria, verificada contra o PRODES.
*Parcela* é uma parte do embarque: uma quantidade que vem de **uma única fazenda**.
Um fornecedor tem uma ou várias fazendas; um embarque tem várias parcelas.

### Tabelas

**`usuario`** — id, email (único), senha_hash, nome, criado_em

**`fornecedor`** — id, usuario_id (FK), nome, documento (CPF/CNPJ, só dígitos, único por usuário),
tipo_pessoa (PF/PJ), email, telefone, municipio, uf, ativo, criado_em, atualizado_em

**`fazenda`** — id, usuario_id, fornecedor_id (FK composta com usuario_id: garante o mesmo dono),
nome, car_codigo (único por usuário), ccir, nirf, matricula, municipio, uf, area_declarada_ha,
`geom GEOMETRY(Geometry, 4326) NOT NULL`, `status` ∈ `pendente | apta | bloqueada`,
area_sobreposta_m2, verificada_em, camada_versao_id, criado_em, atualizado_em

**`documento`** — id, usuario_id, fornecedor_id ou fazenda_id (exatamente um), tipo ∈
`car | ccir | matricula | licenca | contrato | outro`, nome_arquivo, caminho_storage, content_type,
tamanho_bytes, sha256, validade, criado_em. Aceita PDF, PNG e JPG (tipo decidido pelo conteúdo), até 10 MB.

**`camada_versao`** — id, origem, bioma, uf, arquivo, n_feicoes, carregada_em (uma linha por carga)

**`camada_prodes`** — id, versao_id (FK), `geom GEOMETRY(Geometry, 4326)`, ano, class_name, area_km

**`embarque`** — id, usuario_id (FK), identificacao (única por usuário), data_embarque, destino,
`status` ∈ `rascunho | fechado`, fechado_em, criado_em

**`parcela`** — id, embarque_id (FK), fazenda_id (FK, RESTRICT), quantidade_kg (> 0), observacao.
Sem mistura de cargas nem balanço de massa: só a quantidade declarada por fazenda.

**`dossie`** — id, embarque_id (FK, único), gerado_em, `retrato JSONB NOT NULL`,
caminho_geojson, caminho_pdf

### Índices obrigatórios

```sql
CREATE INDEX idx_fazenda_geom ON fazenda        USING GIST (geom);
CREATE INDEX idx_prodes_geom  ON camada_prodes  USING GIST (geom);
```

Sem o índice GiST na camada de referência a checagem fica inviável.

---

## 8. Divisão da aplicação

Três áreas, separadas pelo comportamento no tempo:

| Área | Natureza | Muda quando |
|---|---|---|
| Cadastro (fornecedores, fazendas, documentos) | Dados de base | Raramente |
| Embarques | Transacional | A cada operação de venda |
| Dossiês | Registro imutável | Nunca; só nasce |

### Rotas do frontend

```
/login
/fornecedores            /fornecedores/:id
/fazendas                /fazendas/:id        ← tela de mapa + documentos
/embarques               /embarques/:id       ← abas: composição | evidências
/dossies                 /dossies/:id
```

### Endpoints

```
POST   /auth/registrar
POST   /auth/login                          → { access_token }
GET    /auth/eu

GET    /fornecedores
POST   /fornecedores
GET    /fornecedores/{id}
PUT    /fornecedores/{id}
DELETE /fornecedores/{id}                   → 409 se tiver fazendas
GET    /fornecedores/{id}/documentos
POST   /fornecedores/{id}/documentos        → multipart: arquivo, tipo, validade

GET    /fazendas?fornecedor_id=&status=     → inclui geometria em GeoJSON
POST   /fazendas                            → verifica ao salvar (R1)
POST   /fazendas/import-geojson             → FeatureCollection, tudo ou nada
POST   /fazendas/reverificar                → reprocessa todas (camada atualizada)
GET    /fazendas/{id}
PUT    /fazendas/{id}                       → reverifica se a geometria ou a área mudou
DELETE /fazendas/{id}
POST   /fazendas/{id}/verificar             → reprocessamento manual
GET    /fazendas/{id}/documentos
POST   /fazendas/{id}/documentos

GET    /documentos/{id}/arquivo             → Content-Disposition: attachment
DELETE /documentos/{id}

GET    /embarques
POST   /embarques                           → nasce como rascunho
GET    /embarques/{id}
PUT    /embarques/{id}                      → só em rascunho
DELETE /embarques/{id}                      → só em rascunho
PUT    /embarques/{id}/parcelas             → [{fazenda_id, quantidade_kg}]; valida R2
POST   /embarques/{id}/fechar               → gera o dossiê (R3)

GET    /dossies
GET    /dossies/{id}
GET    /dossies/{id}/geojson                → Content-Disposition: attachment
GET    /dossies/{id}/pdf                    → Content-Disposition: attachment
```

### Transições de estado

```
fazenda:  pendente ──(verificação)──> apta | bloqueada
embarque: rascunho ──(fechar)──> fechado        (não há volta)
```

O fechamento valida R2 de novo: uma fazenda reverificada como bloqueada depois da composição
impede o fechamento.

---

## 9. Checagem espacial

Consulta central:

```sql
SELECT COALESCE(SUM(
         ST_Area(ST_Intersection(f.geom, d.geom)::geography)
       ), 0) AS area_m2
FROM fazenda f
JOIN camada_prodes d ON ST_Intersects(f.geom, d.geom)
WHERE f.id = :id AND d.ano > 2020;
```

Pontos de atenção:

- **O cast `::geography` é obrigatório.** Sem ele, `ST_Area` devolve graus ao quadrado,
  que não significam nada. Um resultado na ordem de 0,0003 indica que o cast está faltando.
- `SUM` porque uma fazenda pode intersectar vários polígonos de supressão.
- `COALESCE` porque sem interseção o `SUM` devolve `NULL`.
- Para geometria em ponto, usar apenas `ST_Intersects`, sem área (R4).
- Se a camada PRODES estiver vazia, o sistema **recusa** a verificação (503) em vez de aprovar tudo em silêncio.
- A implementação está em `services/verificacao.py`; salvar e verificar acontecem na mesma transação (R1).

---

## 10. Dados de referência

**PRODES Cerrado — "Incremento anual na supressão da vegetação nativa", formato shapefile**,
baixado do TerraBrasilis (INPE). Recorte: Minas Gerais.

> **Estado atual (out/2026):** o repositório carrega **PRODES Mata Atlântica / SP** (arquivo
> `data/processed/MataAtlantica_desmatamento_SP.json`) e os imóveis do SICAR de Adamantina, herdados do MVP.
> A carga é parametrizada (`carga_prodes.py --bioma --uf`), então trocar para Cerrado/MG não exige mudar código.
> Atenção: nenhum dos 1.024 imóveis de Adamantina cruza essa camada; por isso o `seed.py` cria uma fazenda
> de demonstração sobre um polígono real do PRODES para exercitar o bloqueio.

Por que esse produto e não os outros:
- O incremento anual carrega o **ano de detecção** em cada polígono, que é o que o filtro
  `ano > 2020` precisa.
- O GeoPackage completo (~1,9 GB) é pesado demais para o orçamento do Azure.
- A máscara acumulada de 2000 é toda anterior à data de corte.
- O Geotiff é raster e exigiria vetorização.

**Antes de carregar**, inspecionar o campo de ano com `gdf.columns` e `gdf['ano'].unique()`.
No Cerrado ele pode vir como inteiro ou como rótulo de período (`2021_2022`). Se for rótulo,
converter para o ano final antes do filtro. Errar aqui faz **toda fazenda sair apta**,
e o erro é silencioso.

Roteiro da carga: `read_file` → `to_crs(4326)` → filtrar `ano > 2020` → `to_postgis` →
criar índice GiST → `ANALYZE`.

### Limitação conhecida, a declarar na documentação

A Comissão Europeia disponibiliza, via Joint Research Centre, um mapa global de cobertura
florestal de 2020 como instrumento de apoio. Não é vinculante, mas tende a ser a referência
consultada do lado europeu. Este projeto usa PRODES por ter maior resolução temática para
o bioma e por ser base oficial brasileira. A comparação entre as duas camadas está em
trabalhos futuros.

---

## 11. Ambiente local

`docker-compose.yml` sobe apenas o banco, imagem `postgis/postgis:16-3.4`.

- Porta **5433** no host (a 5432 costuma estar ocupada por um Postgres local).
- Volume nomeado `pgdata`, senão `docker compose down` apaga a carga do PRODES.
- Scripts em `backend/scripts/init/` rodam **somente na primeira criação do volume**.
- As credenciais ficam gravadas no volume: mudar o `.env` depois exige `docker compose down -v`.

Da máquina, o host é `localhost:5433`. De dentro do Docker, é `db:5432`.

`.env` nunca entra no repositório. `.gitignore` deve incluir `.env` e os arquivos de
shapefile (`*.shp`, `*.dbf`, `*.shx`, `*.prj`, `*.zip`).

---

## 12. Deploy no Azure

Três recursos, mesmo grupo e mesma região (`brazilsouth`, ou `eastus` como alternativa).

| Camada | Serviço | Configuração |
|---|---|---|
| Banco | PostgreSQL Flexible Server | Burstable B1ms, 32 GB |
| Backend | App Service for Containers | Plano Linux B1 |
| Frontend | Static Web Apps | Plano gratuito |

### PostGIS no Azure — leia antes de tentar

`CREATE EXTENSION postgis` **falha** enquanto a extensão não estiver na lista de permitidas
do servidor. Duas etapas, nesta ordem:

1. Adicionar `POSTGIS` ao parâmetro `azure.extensions` do servidor. Isso dispara uma
   implantação que **reinicia** o servidor.
2. Só então conectar e rodar `CREATE EXTENSION postgis;`

```bash
az postgres flexible-server parameter set \
  --resource-group rg-eudr --server-name pg-eudr \
  --name azure.extensions --value POSTGIS
```

### Rede

O servidor recusa conexões externas por padrão. Em Networking: habilitar acesso público,
liberar o IP da máquina de desenvolvimento (para a carga do PRODES) e permitir serviços do
Azure (para o App Service). A conexão exige SSL — acrescentar `?sslmode=require` à URL.

Segredos em Configuration → Application settings, nunca no repositório.

### CORS

Configurar o `CORSMiddleware` do FastAPI com a URL exata do Static Web Apps.
**Configurar em um lugar só**: ativar CORS também no painel do App Service gera cabeçalhos
duplicados, que o navegador rejeita.

### Custo

Criar alerta de orçamento em USD 50 no Cost Management no primeiro dia.
O Flexible Server pode ser parado por até 7 dias, o que zera a cobrança de computação.

---

## 13. Diretrizes de interface

- O mapa é a tela principal do cadastro, não um acessório.
- Status codificado em **cor do traço**: verde (apta), âmbar/vermelho (bloqueada),
  cinza (pendente). Nunca só em texto.
- A camada de supressão fica **por baixo** das fazendas, com hachura diagonal, e deve ser
  desligável. O valor está em ver a sobreposição, não a fazenda isolada.
- Fazenda em ponto: círculo preenchido com um anel tracejado em volta, para deixar claro
  que não há área delimitada.
- Áreas em **hectares** na interface (dividir m² por 10.000). Hectare é a unidade do produtor.
- Fazendas bloqueadas na composição do embarque ficam visíveis e desabilitadas, com o motivo
  ao lado. Nunca ocultas.

---

## 14. Armadilhas conhecidas

| Sintoma | Causa | Saída |
|---|---|---|
| `ST_Area` devolve ~0,0003 | Falta o cast `::geography` | Usar `ST_Area(geom::geography)` |
| Toda fazenda sai apta | SRID divergente, campo de ano errado ou camada vazia | `SELECT COUNT(*), MIN(ano), MAX(ano) FROM camada_prodes` |
| Checagem acima de 10 s | Índice GiST ausente | Criar o índice e rodar `ANALYZE` |
| Mapa com tiles desalinhados | CSS do Leaflet não importado | `import "leaflet/dist/leaflet.css"` no `main.jsx` |
| `Invalid geometry` ao salvar | Polígono com autointerseção | `ST_MakeValid()` ou recusar com 400 |
| `CREATE EXTENSION postgis` falha no Azure | Fora da lista de permitidas | Parâmetro `azure.extensions`, aguardar restart |
| Backend não conecta em produção | Firewall ou SSL ausente | Liberar serviços do Azure, `?sslmode=require` |
| Fazenda em ponto sempre apta | `ST_Area` de ponto é 0 | Tratar ponto com critério binário (R4) |

---

## 15. Convenções

- Validação de geometria no backend, sempre: rejeitar não-polígono/não-ponto, `is_valid`
  falso, área zero, e área acima de 100.000 ha (indica GeoJSON colado por engano).
- Entrada e saída de geometria **sempre em GeoJSON**, nunca WKT. O frontend não conhece WKT.
- Conversão: `shapely.geometry.shape()` na entrada, `ST_AsGeoJSON` ou `mapping()` na saída.
- Erros HTTP com mensagem em português, nomeando o que falhou e o que fazer.
- Migrações com Alembic. Não alterar o schema direto no banco.
- Commits em português, no formato `tipo: descrição` (`feat:`, `fix:`, `infra:`, `docs:`).

---

## 16. Cronograma

| Semana | Entrega |
|---|---|
| 1 | Repositório, Docker, PostGIS, carga do PRODES, autenticação |
| 2 | Modelos e endpoints de fornecedor e fazenda |
| 3 | Frontend com mapa: desenho de polígono e importação de GeoJSON |
| 4 | Checagem espacial e exibição do status |
| 5 | Embarques, fechamento, geração do dossiê (GeoJSON + PDF) |
| 6 | Deploy no Azure, seed, README, apresentação |

Regra: ao fim de cada semana o sistema roda, mesmo que faça pouco. Nunca duas semanas sem
nada funcionando. Se atrasar, cortar escopo (trocar desenho no mapa por só importação de
GeoJSON; trocar PDF por CSV), nunca pular o deploy.

---

## 17. Demonstração

`seed.py` cria: um usuário (`demo@exemplo.com.br`), dois fornecedores, quatro fazendas — três aptas e uma
deliberadamente posicionada sobre área de supressão — e um embarque em rascunho com as três aptas.
Uma das fazendas aptas deve ter até 4 ha e geometria em ponto, para exercitar R4.

Roteiro: abrir o mapa → desenhar fazenda sobre área de desmatamento e ver o bloqueio ao vivo →
tentar incluí-la no embarque e receber a recusa → incluir as aptas → fechar e baixar os arquivos.
