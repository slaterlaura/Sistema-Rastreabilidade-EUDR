# Tutorial: colocar o OrigemCheck no Azure

Passo a passo para publicar o sistema no Azure **do zero**, mantendo a arquitetura de Aplicativo de Funções.
Cada passo diz o que fazer, o porquê, e como conferir que deu certo antes de seguir.

**Tempo estimado:** 1h30 a 2h na primeira vez (boa parte é esperar o Azure criar recursos).

> **Atenção:** estes comandos foram escritos com base na documentação da CLI do Azure, mas **ainda não foram
> executados**. Se algum reclamar de um parâmetro, rode o mesmo comando com `--help` no fim para ver o nome atual da
> opção, ou me mande a mensagem de erro.

---

## O que vamos criar

```
Navegador ──> Static Web Apps (site)  ──> Function App (API)  ──> PostgreSQL + PostGIS (banco)
                                               │
                                               └──> Storage Account (documentos e dossiês)
```

| Recurso | Para quê | Custo aproximado |
|---|---|---|
| Grupo de recursos `rg-eudr` | Uma "pasta" que agrupa tudo; apagar o grupo apaga tudo | zero |
| PostgreSQL Flexible Server (B1ms) | O banco, com a camada PRODES e os cadastros | ~US$ 20–25/mês, ou **zero** se sua assinatura tiver o B1ms gratuito |
| Storage Account | Guarda os arquivos (documentos e dossiês) e o pacote da Function | centavos |
| Function App (Flex Consumption) | A API (o backend FastAPI) | dentro da cota gratuita: 250 mil requisições/mês |
| Static Web Apps (Free) | O site (o frontend React) | zero |

Tudo em **brazilsouth**, menos o Static Web Apps, que não existe lá: ele fica em `eastus2`, mas o site é servido por
uma rede global, então não fica mais lento para quem está no Brasil.

---

## Passo 0. Antes de começar

Você vai precisar:

- da sua conta Azure (Azure for Students) com crédito disponível;
- do **Docker Desktop aberto** (vamos usar o banco local para copiar os dados);
- do projeto atualizado: `cd ~/Desktop/Sistema-Rastreabilidade-EUDR && git pull`.

Use **um terminal só** do começo ao fim. As variáveis que vamos criar valem só para o terminal aberto; se fechar,
rode `source .env.azure` de novo na raiz do projeto.

---

## Passo 1. Instalar as ferramentas do Azure

```bash
brew update
brew install azure-cli
brew tap azure/functions
brew install azure-functions-core-tools@4
```

- `azure-cli` (o comando `az`): cria e configura recursos no Azure pelo terminal.
- `azure-functions-core-tools` (o comando `func`): publica o backend na Function App.

**Conferir:**

```bash
az version
func --version      # deve começar com 4.
```

Agora entre na sua conta (abre o navegador):

```bash
az login
az account show --output table
```

Confira se a assinatura que aparece é a do Azure for Students. Se tiver mais de uma:
`az account set --subscription "Nome da assinatura"`.

### 1.1 Duas conferências importantes

**A região brazilsouth tem o plano Flex?**

```bash
az functionapp list-flexconsumption-locations --output table
```

Procure `brazilsouth` na lista. **Se não aparecer, pare aqui e me avise**: aí usamos `eastus`.

**Sua assinatura tem o PostgreSQL gratuito?** No portal (portal.azure.com), procure **"Serviços gratuitos"**
("Free services") e veja se aparece *Azure Database for PostgreSQL — Flexible Server, B1MS*. Se aparecer, o banco
sai de graça por 12 meses (dentro do limite de 750 horas/mês e 32 GB). Se não aparecer, ele consome uns
US$ 20–25 por mês do seu crédito.

### 1.2 Alerta de orçamento (faça agora, leva 2 minutos)

No portal: **Gerenciamento de Custos → Orçamentos → Adicionar**. Valor US$ 50, alerta por e-mail em 80% e 100%.
Assim você é avisada antes de o crédito acabar.

---

## Passo 2. Nomes e senhas

Os nomes do servidor de banco, da conta de armazenamento e da Function App precisam ser únicos **no Azure inteiro**.
Por isso eles terminam com um sufixo seu.

1. Abra `infra/azure.env.example` e troque `SUFIXO=ls01` por algo seu, com letras minúsculas e números
   (por exemplo `SUFIXO=lslater26`). Salve.

2. Na raiz do projeto, gere o arquivo com as senhas e os nomes:

```bash
cd ~/Desktop/Sistema-Rastreabilidade-EUDR
{
  echo "export PG_SENHA=$(openssl rand -hex 16)Aa1"
  echo "export JWT_SECRET=$(openssl rand -hex 32)"
  cat infra/azure.env.example
} > .env.azure
chmod 600 .env.azure
source .env.azure
```

- `PG_SENHA` é a senha do administrador do banco; `JWT_SECRET` assina os logins do sistema.
- Ambas são aleatórias e ficam **só** no arquivo `.env.azure`, que está no `.gitignore` (não vai para o GitHub).
- `chmod 600` faz só você poder ler o arquivo.

**Conferir** (mostra os nomes, não as senhas):

```bash
echo "$RG | $PG_SERVER | $STORAGE | $APP | $SWA"
```

> Guarde o `.env.azure` com cuidado. Sem ele você perde a senha do banco (dá para redefinir no portal, mas é chato).

---

## Passo 3. O banco de dados

### 3.1 Criar o grupo de recursos

```bash
az group create --name $RG --location $LOCATION
```

Se aparecer o erro `RequestDisallowedByPolicy`, a sua assinatura não permite brazilsouth. Me avise.

### 3.2 Criar o servidor PostgreSQL (leva de 5 a 10 minutos)

```bash
MEU_IP=$(curl -s https://api.ipify.org)

az postgres flexible-server create \
  --resource-group $RG --name $PG_SERVER --location $LOCATION \
  --tier Burstable --sku-name Standard_B1ms --storage-size 32 --version 16 \
  --admin-user $PG_ADMIN --admin-password "$PG_SENHA" \
  --public-access $MEU_IP \
  --yes

az postgres flexible-server db create \
  --resource-group $RG --server-name $PG_SERVER --name eudr
```

O primeiro comando cria o servidor; o segundo cria nele o banco `eudr` (no `db create`, o nome do banco vai em `--name`). Nas versões novas da CLI, `--database-name`
não funciona mais no `create` (só para clusters elásticos), por isso o banco é criado à parte.

- `B1ms` é o menor tamanho (1 vCPU, 2 GB de RAM); dá conta do projeto.
- `--version 16` é a mesma versão do banco local, o que evita surpresas ao copiar os dados.
- `--public-access $MEU_IP` libera o acesso **só do seu computador**. O resto da internet fica bloqueado.

### 3.3 Liberar o acesso da Function ao banco

```bash
az postgres flexible-server firewall-rule create \
  --resource-group $RG --server-name $PG_SERVER \
  --name AllowAzureServices --start-ip-address 0.0.0.0 --end-ip-address 0.0.0.0
```

A faixa `0.0.0.0` é um código especial do Azure que significa "serviços dentro do Azure". A Function não tem um IP
fixo, por isso usamos essa regra.

### 3.4 Habilitar o PostGIS

O Azure só deixa instalar extensões que estejam numa lista de permitidas.

```bash
az postgres flexible-server parameter set \
  --resource-group $RG --server-name $PG_SERVER \
  --name azure.extensions --value POSTGIS
```

Se o comando disser que o servidor vai reiniciar, espere 2 ou 3 minutos antes de seguir.

### 3.5 Criar as tabelas (migrações)

As tabelas são criadas pelas migrações do Alembic, como no banco local. Rodamos da sua máquina, apontando para o
Azure:

```bash
cd backend
source .venv/bin/activate
DATABASE_URL="$DATABASE_URL_AZURE" alembic upgrade head
cd ..
```

**Conferir:** a última linha deve ser `Running upgrade  -> 0001, baseline...`. Se aparecer
`extension "postgis" is not allow-listed`, o passo 3.4 ainda não terminou de valer: espere um pouco e repita.

### 3.6 Copiar os dados do banco local

Vamos copiar tudo o que está no banco local: a camada PRODES (863 mil polígonos) e a conta de demonstração.

**a) Exportar do banco local** (Docker Desktop aberto):

```bash
docker exec eudr-db pg_dump -U eudr -d eudr --data-only -Fc \
  --exclude-table=spatial_ref_sys --exclude-table=alembic_version \
  -f /tmp/eudr.dump
docker cp eudr-db:/tmp/eudr.dump ./eudr.dump
ls -lh eudr.dump
```

- `--data-only`: só os dados; as tabelas já existem no Azure (passo 3.5).
- Ficam de fora `spatial_ref_sys`, que o próprio PostGIS cria, e `alembic_version`, que a migração já gravou.
- O arquivo `eudr.dump` fica na raiz do projeto e está no `.gitignore`.

**b) Importar no Azure** (de 5 a 20 minutos, depende da sua internet):

```bash
docker run --rm --platform linux/amd64 -v "$PWD":/dump \
  -e PGPASSWORD="$PG_SENHA" -e PGSSLMODE=require \
  postgis/postgis:16-3.4 \
  pg_restore --data-only --no-owner --no-privileges --verbose \
    -h $PG_HOST -U $PG_ADMIN -d eudr /dump/eudr.dump 2>&1 | tail -5
```

Usamos o `pg_restore` de dentro da imagem do PostGIS para não precisar instalar nada.

**c) Conferir e otimizar:**

```bash
docker run --rm -e PGPASSWORD="$PG_SENHA" -e PGSSLMODE=require postgis/postgis:16-3.4 \
  psql -h $PG_HOST -U $PG_ADMIN -d eudr -c "ANALYZE;" -c "
    SELECT (SELECT count(*) FROM usuario) AS usuarios,
           (SELECT count(*) FROM fazenda) AS fazendas,
           (SELECT count(*) FROM camada_prodes) AS poligonos_prodes,
           (SELECT status FROM fazenda WHERE nome LIKE 'DEMO%') AS demo;"
```

Deve mostrar: `usuarios 1 | fazendas 4 | poligonos_prodes 863255 | demo bloqueada`.

Depois pode apagar o arquivo: `rm eudr.dump`.

---

## Passo 4. A API (Function App)

### 4.1 Conta de armazenamento e contêiner de arquivos

```bash
az storage account create \
  --name $STORAGE --resource-group $RG --location $LOCATION \
  --sku Standard_LRS --kind StorageV2 \
  --allow-blob-public-access false --min-tls-version TLS1_2

az storage container create --account-name $STORAGE --name $CONTAINER --auth-mode key
```

(Se aparecer um aviso sobre usar a chave da conta, pode ignorar: aqui é só para criar o contêiner.)

O contêiner é **privado**: ninguém baixa arquivo direto dele, só pela API, que confere o login.

### 4.2 Criar a Function App (2 a 3 minutos)

```bash
az functionapp create \
  --resource-group $RG --name $APP --storage-account $STORAGE \
  --flexconsumption-location $LOCATION \
  --runtime python --runtime-version 3.13 \
  --instance-memory 512 --maximum-instance-count 5
```

- `--instance-memory 512`: a menor memória do plano Flex. O app usa uns 115 MB, e memória menor gasta menos da cota
  gratuita.
- `--maximum-instance-count 5`: no máximo 5 cópias da API ao mesmo tempo. Isso protege o banco de abrir conexões
  demais.

Guarde o endereço da API (o Azure pode acrescentar um código ao nome). Usamos `functionapp list` porque, nas versões
atuais da CLI, o `functionapp show` devolve campos vazios para apps do plano Flex:

```bash
export API_HOST=$(az functionapp list -g $RG --query "[?name=='$APP'].defaultHostName | [0]" -o tsv)
echo "export API_HOST=$API_HOST" >> .env.azure
echo $API_HOST
```

### 4.3 Dar à Function acesso aos arquivos

A Function recebe uma "identidade" própria no Azure, e damos a ela permissão de ler e gravar no armazenamento. Assim
não existe senha de armazenamento guardada em lugar nenhum.

```bash
PRINCIPAL_ID=$(az functionapp identity assign -g $RG -n $APP --query principalId -o tsv)
STORAGE_ID=$(az storage account show -n $STORAGE -g $RG --query id -o tsv)
az role assignment create \
  --assignee-object-id $PRINCIPAL_ID --assignee-principal-type ServicePrincipal \
  --role "Storage Blob Data Contributor" --scope $STORAGE_ID
```

A permissão leva alguns minutos para valer.

### 4.4 Configurações da API

São as mesmas variáveis do `.env` local, agora no Azure:

```bash
az functionapp config appsettings set -g $RG -n $APP --settings \
  "DATABASE_URL=$DATABASE_URL_AZURE" \
  "JWT_SECRET=$JWT_SECRET" \
  "TOLERANCIA_M2=1000" \
  "STORAGE_BACKEND=blob" \
  "BLOB_ACCOUNT_URL=https://$STORAGE.blob.core.windows.net" \
  "BLOB_CONTAINER=$CONTAINER" \
  "DB_POOL_SIZE=3" "DB_MAX_OVERFLOW=2" \
  "CORS_ORIGENS=" \
  --output none
```

`CORS_ORIGENS` fica **vazio** no Azure de propósito: lá quem responde ao CORS é a plataforma da Function
(passo 5.3), não o FastAPI. Se os dois respondessem, o cabeçalho sairia duplicado e o navegador bloquearia.

### 4.5 Publicar o backend

```bash
cd backend
func azure functionapp publish $APP --python
cd ..
```

O Azure instala as dependências do `requirements.txt` na nuvem (leva alguns minutos). O `.funcignore` deixa de fora
testes, scripts, migrações e o `.venv`.

### 4.6 Conferir a API

```bash
curl https://$API_HOST/health
curl https://$API_HOST/health/db
```

Devem responder `{"status":"ok"}` e `{"status":"ok","database":"reachable"}`. A **primeira** chamada pode demorar uns
segundos: a Function "acorda" (cold start).

Abra também `https://$API_HOST/docs` no navegador: é a documentação interativa da API.

---

## Passo 5. O site (Static Web Apps)

### 5.1 Criar o site

```bash
az staticwebapp create --name $SWA --resource-group $RG --location eastus2 --sku Free
export SWA_HOST=$(az staticwebapp show -n $SWA -g $RG --query defaultHostname -o tsv)
echo "export SWA_HOST=$SWA_HOST" >> .env.azure
echo $SWA_HOST
```

### 5.2 Gerar e publicar o frontend

O endereço da API entra no site **no momento do build**:

```bash
cd frontend && VITE_API_URL=https://$API_HOST npm run build && cd ..

export SWA_CLI_DEPLOYMENT_TOKEN=$(az staticwebapp secrets list -n $SWA -g $RG --query properties.apiKey -o tsv)
docker run --rm --platform linux/amd64 -e SWA_CLI_DEPLOYMENT_TOKEN \
  -v "$PWD/frontend/dist":/dist node:22-bookworm \
  npx --yes @azure/static-web-apps-cli@2.0.10 deploy /dist --env production
```

Por que dentro do Docker: o publicador do Static Web Apps usa um programa feito para processadores Intel. Num Mac
Apple Silicon sem o Rosetta, rodar `npx @azure/static-web-apps-cli deploy` direto dá `spawn Unknown system error -86`.
O container Intel do Docker Desktop resolve isso sem instalar nada no sistema. É lento (de 5 a 15 minutos).

O `export` é obrigatório: sem ele o token não chega ao container e o publicador tenta um login interativo que expira.
Se terminar com `Deployment Complete`, deu certo.

### 5.3 Deixar o site falar com a API

```bash
az functionapp cors add -g $RG -n $APP --allowed-origins "https://$SWA_HOST"
```

Sem barra no final do endereço.

**Por que na plataforma e não no FastAPI:** no plano Flex, o servidor da plataforma responde sozinho ao `OPTIONS`
(o "preflight" que o navegador faz antes de mandar o token), com 204 e sem cabeçalhos de CORS, antes de a requisição
chegar ao FastAPI. Configurando o CORS na plataforma, ela responde certo. De quebra, esses `OPTIONS` não executam a
função, então não contam na cota.

**Conferir:**

```bash
curl -s -D - -o /dev/null -X OPTIONS https://$API_HOST/fazendas \
  -H "Origin: https://$SWA_HOST" -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: authorization" | grep -i access-control-allow-origin
```

Deve mostrar o endereço do site.

---

## Passo 6. Testar tudo

Abra `https://$SWA_HOST` (rode `echo https://$SWA_HOST` para ver o endereço) e entre com
`demo@exemplo.com.br` / `demo-origemcheck-2026`.

| Teste | O que esperar |
|---|---|
| Quadro de fazendas | 4 fazendas, 3 aptas e 1 bloqueada |
| Mapa | Aproximando em MG, BA ou MA aparece a hachura vermelha do desmatamento |
| Nova fazenda desenhada sobre a hachura | Sai **bloqueada** ao salvar |
| Embarque EMB-DEMO-001 | A fazenda bloqueada aparece desabilitada, com o motivo |
| Anexar um PDF numa fazenda e baixar de volta | Funciona (o arquivo foi para o Blob) |
| Fechar o embarque | Gera o dossiê; o PDF e o GeoJSON baixam |
| Recarregar a página em `/fazendas/1` | Abre normalmente, sem erro 404 |

Para ver se os arquivos foram para o armazenamento:

```bash
az storage blob list --account-name $STORAGE --container-name $CONTAINER --auth-mode key --output table
```

> Depois do teste, se quiser a demonstração "limpa" de novo (embarque em rascunho), me peça e eu desfaço no banco do
> Azure, como fizemos no local.

---

## Passo 7. Guardar e versionar

```bash
git add docs/DEPLOY-AZURE.md infra/azure.env.example infra/azure-functions.sh .gitignore
git commit -m "docs: tutorial de deploy no Azure"
git push
```

O `.env.azure` **não** entra (está no `.gitignore`). Anote em lugar seguro os endereços do site e da API.

---

## Dia a dia depois do deploy

Abra o terminal na raiz do projeto e rode `source .env.azure` antes de qualquer um destes.

**Publicar uma nova versão do backend:**

```bash
cd backend && func azure functionapp publish $APP --python && cd ..
```

**Publicar uma nova versão do frontend:**

```bash
cd frontend && VITE_API_URL=https://$API_HOST npm run build && cd ..
export SWA_CLI_DEPLOYMENT_TOKEN=$(az staticwebapp secrets list -n $SWA -g $RG --query properties.apiKey -o tsv)
docker run --rm --platform linux/amd64 -e SWA_CLI_DEPLOYMENT_TOKEN \
  -v "$PWD/frontend/dist":/dist node:22-bookworm \
  npx --yes @azure/static-web-apps-cli@2.0.10 deploy /dist --env production
```

**Nova migração no banco do Azure:**

```bash
cd backend && DATABASE_URL="$DATABASE_URL_AZURE" alembic upgrade head && cd ..
```

**Carregar uma camada nova do PRODES no Azure** (depois, clique em "Reprocessar camada" no site):

```bash
cd backend
DATABASE_URL="$DATABASE_URL_AZURE" python scripts/carga_prodes.py --arquivo ../data/raw/ARQUIVO.zip --bioma Cerrado
cd ..
```

**Seu IP mudou** (outra rede, internet reiniciou) e o banco recusa a conexão:

```bash
az postgres flexible-server firewall-rule create -g $RG --server-name $PG_SERVER \
  --name MeuIP-$(date +%Y%m%d) --start-ip-address $(curl -s https://api.ipify.org) \
  --end-ip-address $(curl -s https://api.ipify.org)
```

**Economizar crédito quando ninguém estiver usando** (o banco é o único recurso que cobra por hora):

```bash
az postgres flexible-server stop -g $RG -n $PG_SERVER    # para (volta sozinho depois de 7 dias)
az postgres flexible-server start -g $RG -n $PG_SERVER   # liga de novo
```

Com o banco parado, o site abre, mas o login falha.

**Apagar tudo** (irreversível, apaga inclusive o banco):

```bash
az group delete --name $RG
```

---

## Quando algo dá errado

| Erro | Causa provável | O que fazer |
|---|---|---|
| `RequestDisallowedByPolicy` | A assinatura não permite a região | Me avise; trocamos para `eastus` |
| `... is already taken` / `name not available` | Nome já usado por outra pessoa no Azure | Troque o `SUFIXO` no `.env.azure`, rode `source .env.azure` e repita |
| `could not connect` / `timeout` ao rodar migração ou carga | Seu IP não está liberado | Comando "Seu IP mudou", acima |
| `extension "postgis" is not allow-listed` | Passo 3.4 ainda não aplicado | Espere alguns minutos e repita |
| `/health/db` responde `unreachable` | Falta a regra `AllowAzureServices` ou o `DATABASE_URL` está errado | Repita o passo 3.3; confira o passo 4.4 |
| Login no site dá "Não foi possível falar com o servidor" | CORS da plataforma sem o endereço do site, ou API dormindo | Refaça o passo 5.3 (sem `/` no fim) e confira com o `curl` dele; espere o cold start e tente de novo |
| Anexar documento dá erro 500 | A permissão da identidade ainda não valeu | Espere 5 minutos; confira o passo 4.3 |
| Rotas dão 404 com `/api/...` | `host.json` alterado | O `routePrefix` precisa continuar vazio |
| O site abre, mas o login falha | Banco parado | `az postgres flexible-server start ...` |

Se travar, me mande o comando que rodou e a mensagem de erro inteira, **sem** o conteúdo do `.env.azure`.
