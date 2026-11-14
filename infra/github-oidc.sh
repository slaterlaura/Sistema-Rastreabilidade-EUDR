#!/usr/bin/env bash
# Cria a identidade que o GitHub Actions usa para publicar a API na Azure Function (deploy automático).
#
# Por que assim: a conta Azure for Students não pode registrar aplicativos no Entra ID, então não dá para
# criar o "service principal" de sempre. Uma identidade gerenciada atribuída pelo usuário, com credencial
# federada, faz o mesmo papel: o GitHub prova quem é com um token OIDC e nenhuma senha fica guardada no GitHub.
#
# Rodar uma vez, na raiz do projeto:   source .env.azure && bash infra/github-oidc.sh
# No fim, o script imprime os 3 valores para cadastrar no GitHub (ver CONTRIBUTING.md, "Configuração do CI/CD").
set -euo pipefail

: "${RG:?rode antes: source .env.azure}"
: "${APP:?rode antes: source .env.azure}"
REPO="${REPO:-slaterlaura/Sistema-Rastreabilidade-EUDR}"
IDENTIDADE="${IDENTIDADE:-id-github-origemcheck}"
LOCATION="${LOCATION:-brazilsouth}"

echo "==> 1/3 Identidade gerenciada"
az identity create --name "$IDENTIDADE" --resource-group "$RG" --location "$LOCATION" --output none
CLIENT_ID=$(az identity show -n "$IDENTIDADE" -g "$RG" --query clientId -o tsv)
PRINCIPAL_ID=$(az identity show -n "$IDENTIDADE" -g "$RG" --query principalId -o tsv)

echo "==> 2/3 Credencial federada: só o environment 'production' deste repositório pode usar a identidade"
# O GitHub pode mandar o "subject" em dois formatos: o clássico (repo:dono/repo:...) e o novo, com os IDs
# numéricos (repo:dono@ID/repo@ID:...), que passou a valer em repositórios recentes. Cadastramos os dois;
# se faltar o certo, o login falha com AADSTS700213 "No matching federated identity record".
IDS=$(curl -fsS "https://api.github.com/repos/${REPO}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['owner']['id'], d['id'])")
DONO_ID=${IDS% *}; REPO_ID=${IDS#* }
DONO=${REPO%%/*}; NOME_REPO=${REPO#*/}
for par in "github-production|repo:${REPO}:environment:production" \
           "github-production-ids|repo:${DONO}@${DONO_ID}/${NOME_REPO}@${REPO_ID}:environment:production"; do
  az identity federated-credential create \
    --name "${par%%|*}" --identity-name "$IDENTIDADE" --resource-group "$RG" \
    --issuer https://token.actions.githubusercontent.com \
    --subject "${par#*|}" \
    --audiences api://AzureADTokenExchange --output none
done

echo "==> 3/3 Permissão mínima: publicar só nesta Function App"
APP_ID=$(az functionapp list -g "$RG" --query "[?name=='$APP'].id | [0]" -o tsv)
az role assignment create --assignee-object-id "$PRINCIPAL_ID" --assignee-principal-type ServicePrincipal \
  --role "Website Contributor" --scope "$APP_ID" --output none

cat <<FIM

Pronto. Cadastre no GitHub (Settings → Environments → production → Environment secrets):
  AZURE_CLIENT_ID       = $CLIENT_ID
  AZURE_TENANT_ID       = $(az account show --query tenantId -o tsv)
  AZURE_SUBSCRIPTION_ID = $(az account show --query id -o tsv)
FIM
