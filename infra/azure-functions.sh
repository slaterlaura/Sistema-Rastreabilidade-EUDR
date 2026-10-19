#!/usr/bin/env bash
# Provisiona o backend no Azure Functions (plano Flex Consumption, Python 3.13).
#
# ATENÇÃO: este script NÃO foi executado pelo autor (a CLI do Azure não estava disponível no ambiente
# em que foi escrito). Antes de rodar, confira cada comando com `az <grupo> <comando> --help` e rode
# por etapas, copiando e colando, na primeira vez.
#
# Pré-requisitos: `az login`, o PostgreSQL Flexible Server já criado e as variáveis abaixo exportadas.
#   export DATABASE_URL='postgresql+psycopg2://USUARIO:SENHA@SERVIDOR.postgres.database.azure.com:5432/eudr?sslmode=require'
#   export JWT_SECRET="$(openssl rand -hex 32)"
#   export CORS_ORIGENS='https://SEU-SITE.azurestaticapps.net'
set -euo pipefail

: "${DATABASE_URL:?exporte DATABASE_URL (com ?sslmode=require)}"
: "${JWT_SECRET:?exporte JWT_SECRET (openssl rand -hex 32)}"
: "${CORS_ORIGENS:?exporte CORS_ORIGENS (URL exata do Static Web Apps)}"

RG="${RG:-rg-eudr}"
LOCATION="${LOCATION:-brazilsouth}"        # confirme com: az functionapp list-flexconsumption-locations
STORAGE="${STORAGE:-steudrarquivos}"        # 3-24 caracteres, minúsculas e números, único no Azure
APP="${APP:-func-origemcheck}"              # vira https://$APP.azurewebsites.net
PG_SERVER="${PG_SERVER:-pg-eudr}"
CONTAINER="${CONTAINER:-origemcheck-arquivos}"
MEMORIA_MB="${MEMORIA_MB:-512}"             # 512 gasta 4x menos GB-s da cota gratuita que 2048
MAX_INSTANCIAS="${MAX_INSTANCIAS:-5}"       # instâncias x (pool+overflow) tem de caber no max_connections do PostgreSQL

echo "==> 1/7 Grupo de recursos"
az group create --name "$RG" --location "$LOCATION"

echo "==> 2/7 Conta de armazenamento (arquivos do sistema e pacote da Function) e contêiner privado"
az storage account create --name "$STORAGE" --resource-group "$RG" --location "$LOCATION" \
  --sku Standard_LRS --kind StorageV2 --min-tls-version TLS1_2 --allow-blob-public-access false
az storage container create --account-name "$STORAGE" --name "$CONTAINER" --auth-mode login

echo "==> 3/7 Function App (Flex Consumption, Python 3.13)"
az functionapp create --resource-group "$RG" --name "$APP" --storage-account "$STORAGE" \
  --flexconsumption-location "$LOCATION" --runtime python --runtime-version 3.13 \
  --instance-memory "$MEMORIA_MB" --maximum-instance-count "$MAX_INSTANCIAS"

echo "==> 4/7 Identidade gerenciada com acesso ao Blob (sem chave de armazenamento nas configurações)"
PRINCIPAL_ID="$(az functionapp identity assign --resource-group "$RG" --name "$APP" --query principalId -o tsv)"
STORAGE_ID="$(az storage account show --name "$STORAGE" --resource-group "$RG" --query id -o tsv)"
az role assignment create --assignee-object-id "$PRINCIPAL_ID" --assignee-principal-type ServicePrincipal \
  --role "Storage Blob Data Contributor" --scope "$STORAGE_ID"

echo "==> 5/7 Escala HTTP (concorrência baixa por instância protege o pool de conexões)"
az functionapp scale config set --resource-group "$RG" --name "$APP" \
  --maximum-instance-count "$MAX_INSTANCIAS" --instance-memory "$MEMORIA_MB" \
  --trigger-type http --trigger-settings perInstanceConcurrency=8

echo "==> 6/7 Configurações do aplicativo (segredos ficam aqui, nunca no repositório)"
az functionapp config appsettings set --resource-group "$RG" --name "$APP" --settings \
  "DATABASE_URL=$DATABASE_URL" \
  "JWT_SECRET=$JWT_SECRET" \
  "CORS_ORIGENS=$CORS_ORIGENS" \
  "TOLERANCIA_M2=${TOLERANCIA_M2:-1000}" \
  "STORAGE_BACKEND=blob" \
  "BLOB_ACCOUNT_URL=https://${STORAGE}.blob.core.windows.net" \
  "BLOB_CONTAINER=$CONTAINER" \
  "DB_POOL_SIZE=3" "DB_MAX_OVERFLOW=2"
# CORS: NÃO configure CORS no painel/CLI da Function. O FastAPI já responde (CORSMiddleware);
# configurar nos dois lugares duplica os cabeçalhos e o navegador recusa.

echo "==> 7/7 PostgreSQL: libera os serviços do Azure e habilita o PostGIS"
az postgres flexible-server firewall-rule create --resource-group "$RG" --name "$PG_SERVER" \
  --rule-name AllowAzureServices --start-ip-address 0.0.0.0 --end-ip-address 0.0.0.0
az postgres flexible-server parameter set --resource-group "$RG" --server-name "$PG_SERVER" \
  --name azure.extensions --value POSTGIS      # reinicia o servidor; só depois rode CREATE EXTENSION (a migração 0001 faz isso)

cat <<MSG

Pronto. Próximos passos (da sua máquina):
  1) Libere seu IP no firewall do PostgreSQL:
       az postgres flexible-server firewall-rule create -g $RG -n $PG_SERVER --rule-name MeuIP \\
         --start-ip-address <SEU_IP> --end-ip-address <SEU_IP>
  2) Migração e dados:  export DATABASE_URL=...; cd backend; alembic upgrade head
                        python scripts/carga_prodes.py ...; python scripts/seed.py
  3) Publicar o código: cd backend && func azure functionapp publish $APP --python   (ou use o workflow do GitHub)
  4) Crie o alerta de orçamento de USD 50 em Cost Management.
MSG
