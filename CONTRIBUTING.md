# Como contribuir

Guia para quem vai mexer no OrigemCheck. Para entender o sistema por dentro, leia antes
[docs/COMO-FUNCIONA.md](docs/COMO-FUNCIONA.md).

O site já está no ar. Por isso nada vai direto para a `main`: toda mudança de código passa por um **pull request (PR)**,
os testes rodam sozinhos no GitHub e a Laura aprova. Quando o PR entra na `main`, o GitHub publica a nova versão no
Azure automaticamente.

---

## Que tipo de mudança é a sua?

| Quero… | Como | Precisa de PR? |
|---|---|---|
| Mudar código (backend ou frontend) | Branch → PR → aprovação → merge | **Sim**; o deploy é automático |
| Mudar o banco (tabela, coluna) | Junto do código, com uma migração do Alembic (ver abaixo) | **Sim**; a Laura aplica a migração no Azure antes do merge |
| Carregar dados de referência (PRODES, imóveis do CAR) | Script `carga_*.py` apontando para o Azure | Não; é dado, não é código |
| Cadastrar fazendas, fornecedores, embarques | Pelo site | Não |

---

## 1. Preparar a máquina (uma vez)

Precisa de: Git, Docker Desktop, Python 3.13 e Node 22.

```bash
git clone https://github.com/slaterlaura/Sistema-Rastreabilidade-EUDR.git
cd Sistema-Rastreabilidade-EUDR
cp .env.example .env              # ajuste as senhas; DATABASE_URL usa a mesma senha do Postgres
docker compose up -d              # banco local (PostgreSQL + PostGIS, porta 5433)

cd backend
python3.13 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
alembic upgrade head              # cria as tabelas no banco local
python scripts/carga_prodes.py --arquivo ../data/processed/MataAtlantica_desmatamento_SP.json \
    --bioma "Mata Atlantica" --uf SP
python scripts/seed.py            # conta demo: demo@exemplo.com.br / demo-origemcheck-2026
cd ../frontend && npm install
```

Para rodar: `uvicorn app.main:app --reload` em `backend/` e `npm run dev` em `frontend/` (http://localhost:5173).

---

## 2. Fazer uma mudança de código

```bash
git checkout main && git pull                  # parte sempre da main atualizada
git checkout -b nome-curto-da-mudanca          # ex.: camada-imoveis, corrige-pdf
# ... edite, teste localmente ...
cd backend && python -m pytest tests -q && cd ..        # testes do backend
cd frontend && npm run build && cd ..                    # typecheck + build do frontend
git add -A && git commit -m "feat: o que mudou e por quê"
git push -u origin nome-curto-da-mudanca
```

Depois abra o PR no GitHub (aparece um botão "Compare & pull request").

**Commits** em português, no formato `tipo: descrição` (`feat:`, `fix:`, `docs:`, `infra:`, `test:`).

### O que acontece no PR

Dois checks rodam sozinhos, e os dois precisam ficar verdes:

| Check | O que faz |
|---|---|
| `backend / testes` | Sobe um PostgreSQL + PostGIS, roda todos os testes e o `alembic check` (confere que toda mudança de modelo tem migração) |
| `frontend / build` | Instala as dependências, roda o typecheck e gera o build do site |

Se algum ficar vermelho, clique em "Details" para ver o erro, corrija na mesma branch e faça push de novo: o PR atualiza
sozinho. Com os checks verdes, a **Laura revisa e aprova**, e o merge pode ser feito.

### O que acontece no merge

O GitHub publica no Azure **só o que mudou**:
- mudou `backend/` → publica a API na Azure Function e testa `/health/db`;
- mudou `frontend/` → gera o site e publica no Static Web Apps.

Dá para acompanhar na aba **Actions**. Em 3 a 8 minutos a versão nova está no ar.

---

## 3. Mudanças no banco (migrações)

O banco **nunca** é alterado na mão. Toda mudança é uma migração do Alembic, que vem no mesmo PR do código.

```bash
cd backend
# 1) altere app/models.py
# 2) gere a migração e CONFIRA o arquivo gerado em alembic/versions/
alembic revision --autogenerate -m "descrição curta"
# 3) aplique no banco local e rode os testes
alembic upgrade head && python -m pytest tests -q
```

**No Azure, a migração não roda sozinha** (o GitHub não tem IP fixo para passar no firewall do banco). Antes do merge
de um PR com migração, a Laura aplica:

```bash
source .env.azure
cd backend && DATABASE_URL="$DATABASE_URL_AZURE" alembic upgrade head
```

Por isso, toda migração tem de ser **compatível com a versão anterior do código**: acrescentar coluna ou tabela pode;
apagar ou renomear exige dois PRs (primeiro o código para de usar, depois a migração remove).

---

## 4. Carregar dados de referência

São camadas comuns a todos os usuários: o desmatamento do PRODES e, em breve, os imóveis do CAR. Elas entram por
script, da sua máquina, direto no banco do Azure.

Você vai precisar que a Laura:
1. passe a `DATABASE_URL` de **carga**: um usuário do banco que só consegue mexer nas camadas, sem acesso a contas e
   cadastros;
2. libere o **seu IP** no firewall do banco (ele muda de tempos em tempos; descubra o atual em https://api.ipify.org).

Os arquivos baixados ficam em `data/raw/` (fora do git). Exemplo com o PRODES:

```bash
cd backend && source .venv/bin/activate
DATABASE_URL="<url de carga que a Laura passou>" \
  python scripts/carga_prodes.py --arquivo ../data/raw/ARQUIVO.zip --bioma Cerrado
```

Depois de uma carga do PRODES, alguém clica em **Fazendas → Reprocessar camada** no site.

### Imóveis do CAR (base comum a todos)

Baixe o shapefile **"Área do Imóvel"** do município ou estado no SICAR (consulta pública do CAR) e salve em `data/raw/`.
Não precisa converter nem renomear colunas: o script reconhece os nomes do SICAR, em maiúsculas ou minúsculas.

```bash
cd backend && source .venv/bin/activate
DATABASE_URL="<url de carga que a Laura passou>" \
  python scripts/carga_imoveis.py --arquivo ../data/raw/AREA_IMOVEL.zip
```

- Carregar outro município **soma** à base; recarregar o mesmo **atualiza**. Nada é apagado.
- `--uf MG` carrega só um estado de um arquivo maior; `--somente-converter saida.geojson` gera o GeoJSON sem tocar no banco.
- No site, os imóveis aparecem no chip **Imóveis CAR** do mapa, para todas as contas, e em **Nova fazenda → Imóvel do CAR**,
  onde basta clicar no imóvel para cadastrá-lo como fazenda.

Teste sempre primeiro no banco **local** (sem a `DATABASE_URL` na frente do comando).

---

## Dúvidas comuns

- **"Required status check is expected" e o merge não libera:** os checks ainda estão rodando ou falharam; veja a aba Checks.
- **Conflito com a main:** `git checkout main && git pull && git checkout sua-branch && git merge main`, resolva, faça push.
- **Testes passam local e falham no GitHub:** o GitHub usa um banco limpo. Confira se o teste não depende de dados que
  só existem na sua máquina.
- **Mudei só o README:** os checks rodam mesmo assim (são rápidos), e não há deploy.
