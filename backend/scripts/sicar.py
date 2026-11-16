#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
origemcheck_estudo.py - guia de consulta do projeto OrigemCheck (Sistema de Rastreabilidade EUDR).

Uso (só biblioteca padrão, Python 3.8+):
    python origemcheck_estudo.py                 -> lista os tópicos
    python origemcheck_estudo.py 4               -> mostra o tópico 4
    python origemcheck_estudo.py banco           -> mostra o tópico cujo nome/apelido contém "banco"
    python origemcheck_estudo.py buscar 403      -> procura "403" em todo o conteúdo
    python origemcheck_estudo.py tabelas         -> tabela de referência rápida (também: endpoints, status,
                                                    regras, azure, numeros, comandos)
    python origemcheck_estudo.py prova           -> prova interativa de 15 questões
    python origemcheck_estudo.py tudo            -> imprime tudo
"""
import random
import sys
import textwrap
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

LARGURA = 100


# =====================================================================================================
# 1. DADOS DE REFERÊNCIA RÁPIDA
# =====================================================================================================

PROJETO = {
    "nome": "OrigemCheck",
    "repositorio": "https://github.com/slaterlaura/Sistema-Rastreabilidade-EUDR",
    "versao_entregue": "commit 2e560ba (branch main, 15/11/2026)",
    "site": "https://kind-pebble-04924410f.3.azurestaticapps.net",
    "api": "https://func-origemcheck-lslater26.azurewebsites.net",
    "docs_api": "https://func-origemcheck-lslater26.azurewebsites.net/docs",
    "regulamento": "Regulamento (UE) 2023/1115 (EUDR), alterado pelo 2025/2650",
    "data_de_corte": "31/12/2020",
    "vale_a_partir_de": "30/12/2026 (médio e grande porte); 30/06/2027 (micro e pequenas)",
    "cenario_alvo": "exportador de café de médio porte, ~15 embarques/mês",
    "personas": "Mariana (analista, opera) | Roberto (sócio, consulta) | Klaus (importador, só recebe o dossiê)",
}

REGRAS_DE_NEGOCIO: Dict[str, str] = {
    "R1": "Verificação automática: salvar ou alterar a geometria já verifica, na MESMA transação. Nunca existe "
          "fazenda salva e não verificada. Sem camada PRODES carregada -> 503 e nada é salvo.",
    "R2": "Fazenda não apta não compõe embarque. Validação no SERVIDOR (400 nomeando as fazendas). O fechamento "
          "valida de novo, porque a camada pode ter mudado.",
    "R3": "Dossiê é retrato congelado: copia geometrias, CAR, status, área sobreposta, versão da camada, kg e "
          "documentos com SHA-256 (coluna JSONB dossie.retrato). Não muda quando o PRODES muda.",
    "R4": "Ponto só para áreas de até 4 ha. Para ponto o critério é binário: cai dentro da supressão = bloqueada.",
    "R5": "Sobreposição abaixo de TOLERANCIA_M2 (padrão 1.000 m²) não bloqueia (fica registrada). Não vale p/ ponto.",
    "R6": "Cada conta só vê o que é seu. Recurso de outra conta responde 404 (não 403), para não revelar que existe.",
    "extra": "Só conta classe DESMATAMENTO com ano > 2020; CAR e CPF/CNPJ únicos por conta; fazenda em embarque não "
             "pode ser excluída; identificação do embarque única por conta; embarque fechado é imutável; mesma "
             "fazenda não repete na composição; geometria > 100.000 ha é recusada.",
}

STATUS_HTTP: Dict[int, str] = {
    200: "OK.",
    201: "Criado (ex.: POST /fazendas devolve a fazenda já verificada).",
    204: "Excluído, sem corpo.",
    400: "Pedido inválido: geometria ruim, fazenda bloqueada no embarque, embarque vazio, formato de arquivo.",
    401: "Sem token, token vencido (8 h) ou adulterado. Traz WWW-Authenticate: Bearer. O site volta ao login.",
    403: "NÃO É USADO. Recurso de outra conta responde 404 (R6).",
    404: "Não existe OU é de outra conta. Também: rota não registrada (faltou include_router).",
    409: "Conflito: e-mail/CAR/CPF repetido, fornecedor com fazendas, fazenda em embarque, embarque já fechado.",
    410: "Arquivo sumiu do armazenamento (registro existe, arquivo não).",
    413: "Upload maior que 10 MB.",
    422: "Corpo não bate com o schema Pydantic (campo faltando/tipo errado, CPF inválido).",
    503: "Não há camada PRODES carregada para verificar (R1).",
}

ENDPOINTS: List[Tuple[str, str, str]] = [
    ("GET", "/health", "app no ar (público)"),
    ("GET", "/health/db", "SELECT 1 no banco: reachable/unreachable (público; usado no smoke test)"),
    ("POST", "/auth/registrar", "cria conta (público) -> 201; 409 e-mail repetido"),
    ("POST", "/auth/login", "e-mail+senha -> access_token JWT (público); 401 se errado"),
    ("GET", "/auth/eu", "dados da conta logada"),
    ("GET/POST", "/fornecedores", "listar/criar"),
    ("GET/PUT/DELETE", "/fornecedores/{id}", "detalhar/editar/excluir (409 se tem fazendas)"),
    ("GET/POST", "/fazendas", "listar/criar (cria JÁ verificando, R1)"),
    ("GET/PUT/DELETE", "/fazendas/{id}", "detalhar/editar (reverifica se mudar geometria)/excluir"),
    ("POST", "/fazendas/import-geojson", "importa FeatureCollection, tudo ou nada"),
    ("POST", "/fazendas/{id}/verificar", "reverifica uma fazenda"),
    ("POST", "/fazendas/reverificar", "reverifica todas da conta (botão Reprocessar camada)"),
    ("GET/POST", "/fornecedores/{id}/documentos", "listar/anexar (multipart)"),
    ("GET/POST", "/fazendas/{id}/documentos", "listar/anexar (multipart)"),
    ("GET", "/documentos/{id}/arquivo", "baixar"),
    ("DELETE", "/documentos/{id}", "excluir"),
    ("GET/POST", "/embarques", "listar/criar (nasce rascunho)"),
    ("GET/PUT/DELETE", "/embarques/{id}", "detalhar/editar/excluir (só rascunho)"),
    ("PUT", "/embarques/{id}/parcelas", "compõe kg por fazenda (recusa não aptas, R2)"),
    ("POST", "/embarques/{id}/fechar", "fecha e gera o dossiê (R2 + R3)"),
    ("GET", "/dossies", "lista dossiês"),
    ("GET", "/dossies/{id}", "detalhe (retrato)"),
    ("GET", "/dossies/{id}/geojson", "baixa GeoJSON"),
    ("GET", "/dossies/{id}/pdf", "baixa PDF"),
    ("GET", "/camada/versao", "número da última carga (vai na URL dos recortes p/ invalidar cache)"),
    ("GET", "/camada/prodes?bbox=...", "polígonos PRODES do recorte (zoom >= 10), até 3.000"),
    ("GET", "/camada/prodes/calor?nivel=&bbox=", "mapa de calor (nível 0: 0,25°; nível 1: 0,05°)"),
    ("GET", "/imoveis?bbox=...", "contornos de imóveis do CAR (zoom >= 12)"),
    ("GET", "/imoveis/{cod_imovel}", "um imóvel do CAR"),
]

# família 1 = dados de cada exportador (mutáveis, via API, filtrados por usuario_id)
# família 2 = camadas de referência (comuns a todos, só mudam por script de carga)
TABELAS: Dict[str, Tuple[str, str]] = {
    "usuario": ("exportador", "conta: e-mail (único), senha_hash (bcrypt), nome"),
    "fornecedor": ("exportador", "de quem compra: documento CPF/CNPJ (único por conta), tipo PF/PJ, nome, município, uf, ativo"),
    "fazenda": ("exportador", "geom (Polygon/MultiPolygon/Point, SRID 4326, GiST), status pendente/apta/bloqueada, "
                              "area_sobreposta_m2, verificada_em, camada_versao_id, car_codigo (único por conta)"),
    "documento": ("exportador", "arquivo anexado: dono = fornecedor OU fazenda (exatamente um), tipo, caminho_storage, sha256, validade"),
    "embarque": ("exportador", "remessa: identificacao (única por conta), data, destino, status rascunho/fechado, fechado_em"),
    "parcela": ("exportador", "kg de uma fazenda num embarque; quantidade_kg > 0; fazenda_id ON DELETE RESTRICT"),
    "dossie": ("exportador (mas IMUTÁVEL)", "retrato JSONB congelado + caminho_geojson + caminho_pdf; um por embarque"),
    "camada_versao": ("camada", "carimbo de cada carga do PRODES: bioma, uf, arquivo, n_feicoes, carregada_em"),
    "camada_prodes": ("camada", "~863 mil polígonos de desmatamento 2021-2026 (735 MB, quase todo o banco); geom GiST, ano"),
    "prodes_calor": ("camada (derivada)", "resumo em células p/ mapa de calor: ~7,8 mil (nível 0) e ~101 mil (nível 1)"),
    "imovel_versao": ("camada", "carimbo de cada carga de imóveis do CAR"),
    "imovel": ("camada", "base do CAR: cod_imovel (único), município, uf, área, situação, geom GiST"),
    "alembic_version": ("controle", "em qual migração o banco está"),
}

QUEM_MEXE_NO_BANCO: Dict[str, str] = {
    "usuário do site": "NUNCA toca no banco. Pede à API; a API só mostra/altera linhas da conta dele.",
    "API (local)": "usuário de banco eudr (do .env, docker na porta 5433).",
    "API (Azure)": "administrador eudradmin. (Melhoria possível: usuário só para a aplicação = menor privilégio.)",
    "carga": "scripts carga_prodes.py / carga_imoveis.py. Só SELECT/INSERT/UPDATE/DELETE nas 5 tabelas de camada. "
             "NÃO enxerga contas, fazendas, embarques, dossiês. Criado por infra/papel-carga.sql; teste confere.",
    "administradora (Laura)": "eudradmin: migrações (alembic upgrade head), firewall, cargas.",
    "barreiras": "firewall recusa tudo exceto serviços Azure e IPs liberados; SSL obrigatório; senhas fora do git; "
                 "backup diário com retenção de 7 dias.",
}

RECURSOS_AZURE: Dict[str, str] = {
    "rg-eudr": "grupo de recursos (assinatura Azure for Students, crédito USD 100)",
    "pg-origemcheck-lslater26": "PostgreSQL Flexible Server, Burstable B1ms, 32 GB, PG16 + PostGIS, Brazil South. "
                                "Único cobrado por hora ligado: ~US$ 20-25/mês (ou zero com B1ms grátis 12 meses).",
    "func-origemcheck-lslater26": "Azure Functions Flex Consumption, Python 3.13, 512 MB, até 5 instâncias, 0 sempre prontas. "
                                  "Cota grátis: 250 mil execuções e 100 mil GB-s/mês.",
    "storigemchecklslater26": "Storage Account Standard LRS, contêiner PRIVADO origemcheck-arquivos (documentos e dossiês).",
    "swa-origemcheck-lslater26": "Static Web Apps plano Free, East US 2 (não existe em Brazil South; rede global).",
    "id-github-origemcheck": "identidade gerenciada com credencial federada (OIDC) p/ o GitHub publicar; papel Website Contributor.",
}

NUMEROS: Dict[str, str] = {
    "tolerância": "1.000 m² (TOLERANCIA_M2)",
    "ponto": "até 4 ha",
    "geometria máxima": "100.000 ha",
    "polígonos PRODES": "~863 mil, 2021 a 2026, seis biomas, 735 MB",
    "tempo de verificação": "~0,1 s por fazenda (medido 6 a 161 ms)",
    "token JWT": "HS256, validade 8 horas",
    "senha": "8 a 72 caracteres, hash bcrypt",
    "upload": "PDF/PNG/JPEG pelos primeiros bytes, até 10 MB",
    "pool de conexões": "3 + 2 por instância x 5 instâncias = máx. 25 (limite B1ms ~50)",
    "cache React Query": "5 minutos; dossiê staleTime Infinity; retry até 2x só p/ erro não-4xx",
    "cache camada": "Cache-Control private, max-age=3600 (1 h)",
    "recorte do mapa": "até 3.000 feições, simplificadas, grade de 0,25°",
    "timeout Function": "3 min 30 s (host.json); conexão ao banco 10 s",
    "smoke test": "/health/db até 20 vezes a cada 15 s (~5 min)",
    "testes": "106 funções em 13 arquivos = 112 casos; passaram em 53 s",
    "backup": "diário, 7 dias de retenção",
    "memória da app": "pico ~115 MB, import em 0,6 s",
    "alerta de orçamento": "US$ 50 (avisos em 80% e 100%)",
}

COMANDOS: Dict[str, str] = {
    "subir banco local": "docker compose up -d        (PostgreSQL 16 + PostGIS 3.4, porta 5433)",
    "criar tabelas": "cd backend && alembic upgrade head",
    "carregar PRODES de exemplo": "python scripts/carga_prodes.py --arquivo ../data/processed/MataAtlantica_desmatamento_SP.json "
                                  "--bioma \"Mata Atlantica\" --uf SP",
    "dados de demonstração": "python scripts/seed.py   (e scripts/seed_imoveis.py p/ PE, MA, RS)",
    "rodar API": "uvicorn app.main:app --reload   -> http://localhost:8000 (docs em /docs)",
    "rodar site": "cd frontend && npm run dev   -> http://localhost:5173",
    "testes": "cd backend && python -m pytest tests -q   (banco eudr_test recriado)",
    "nova migração": "alembic revision --autogenerate -m \"descricao\"  -> conferir arquivo -> alembic upgrade head -> alembic check",
    "build do site": "npm run build   (inclui tsc -b, checagem de tipos)",
    "Function local": "cp local.settings.sample.json local.settings.json && func start   (porta 7071; não testado)",
    "desligar banco Azure": "az postgres flexible-server stop ...   (zera computação por até 7 dias)",
    "apagar tudo na Azure": "az group delete --name rg-eudr",
}


# =====================================================================================================
# 2. TÓPICOS (texto explicativo)
# =====================================================================================================

@dataclass
class Topico:
    titulo: str
    apelidos: List[str]
    texto: str
    extras: List[str] = field(default_factory=list)


TOPICOS: List[Topico] = [
    Topico("O problema e a ideia geral", ["problema", "eudr", "ideia", "resumo", "restaurante"], """
A Europa só compra café (e cacau, soja, gado, palma, borracha, madeira) que NÃO venha de área desmatada depois de
31/12/2020 (Regulamento UE 2023/1115, EUDR). A obrigação é do importador europeu, que repassa ao exportador por
contrato: para cada remessa precisa da geolocalização de cada área de origem + evidência de que não houve
desmatamento depois da data de corte + evidência de legalidade.

O OrigemCheck guarda o desenho de cada fazenda, compara automaticamente com o mapa oficial de desmatamento do INPE
(PRODES) e, para cada embarque, gera um dossiê (GeoJSON + PDF) que NÃO muda depois.

Projeto NÃO extensionista: sem organização parceira. Problema modelado pelo regulamento + cenário-alvo (exportador
de café de médio porte, ~15 embarques/mês, hoje controla tudo em planilhas e e-mails).

Três fragilidades do jeito antigo: (1) técnica: cruzar polígonos exige SIG; (2) controle: nada impede fazenda com
problema de entrar no embarque; (3) prova: se o mapa muda depois, a planilha não registra o que se sabia na data.

Analogia do restaurante:
- site = salão e cardápio (onde você vê e clica)
- API = garçom + cozinha (recebe o pedido, confere regras, faz o trabalho)
- banco = despensa e arquivo de fichas
- Blob Storage = armário de pastas (PDFs, documentos, dossiês)
O cliente nunca entra na cozinha: O SITE NUNCA FALA COM O BANCO, SÓ COM A API.

Fora do escopo: lotes/mistura/balanço de massa; Ibama, terras indígenas, UCs; portal do importador; perfis e trilha de
auditoria; filas/jobs; IA/OCR.
"""),

    Topico("Arquitetura: as peças e onde moram", ["arquitetura", "pecas", "azure", "camadas", "componentes"], """
Fluxo físico quando você abre o site:
1. O navegador baixa o site UMA VEZ do Azure Static Web Apps (só arquivos HTML/JS/CSS; não sabe nada dos dados).
2. Esse JavaScript (React) pede tudo à API por HTTPS, recebendo JSON.
3. A API (FastAPI dentro do Azure Functions) confere quem é você, aplica as regras e consulta o PostgreSQL+PostGIS.
4. Se há arquivo (documento, PDF do dossiê), a API grava/lê no Blob Storage.

Tudo no grupo de recursos rg-eudr. Banco, API e Blob em Brazil South. Site em East US 2 (Static Web Apps não existe
no Brasil; é entregue por rede global, então não fica lento).

Fora da nuvem: scripts de carga (PRODES, CAR) rodam da máquina de desenvolvimento direto no banco, com o usuário
carga, por SSL e IP liberado no firewall. Pipeline: GitHub Actions (frontend.yml e backend.yml).

"Três camadas" no sentido de arquitetura = site / API / banco. (Não confundir com "camada de referência" do banco.)
"""),

    Topico("Fluxo: login e token", ["login", "token", "jwt", "autenticacao", "bcrypt", "401"], """
1. Você digita e-mail e senha -> site manda POST /auth/login.
2. API procura o usuário pelo e-mail. A senha NUNCA é guardada: o banco tem só o hash bcrypt (com salt). A API faz
   o hash do que você digitou e compara (conferir_senha em app/auth.py).
3. Se bater, criar_token() gera um JWT (pulseira de festa): sub = id do usuário, exp = 8 h, assinado com HS256 e
   JWT_SECRET (só a API conhece; falsificar quebra a assinatura).
4. O site guarda no localStorage e manda em TODO pedido: Authorization: Bearer <token>.
5. Em cada rota protegida, usuario_atual() lê o cabeçalho (HTTPBearer), valida assinatura e validade (python-jose)
   e confere se o usuário ainda existe.
6. Token ausente/vencido/adulterado -> 401 + WWW-Authenticate: Bearer. O api.ts apaga o token, dispara o evento
   origemcheck:sessao-expirada, o AuthProvider limpa o cache e a rota Protegida manda para /login.

Por que JWT próprio e não Entra ID (login Microsoft)? Conta de estudante não registra aplicativos no Entra ID e o
escopo era um login por exportador, sem perfis. A Function é anônima na plataforma; a segurança é o token.

Fragilidade conhecida: token no localStorage pode ser lido por script em caso de XSS. Sem recuperação de senha e sem
limite de tentativas de login.
"""),

    Topico("Fluxo: cadastrar fazenda e verificar (coração do sistema)", ["fazenda", "verificacao", "cadastro", "r1", "r4", "r5", "postgis"], """
1. Você desenha no mapa (polígono clicando nos cantos, ponto, ou clica num imóvel do CAR) ou importa GeoJSON.
   O site transforma em GeoJSON (texto com coordenadas).
2. Site manda POST /fazendas (fornecedor_id, nome, geometry, dados).
3. API: usuario_atual() + obter_fornecedor() (o fornecedor é seu? R6).
4. services/geometria.py valida: ST_GeomFromGeoJSON, ST_MakeValid (conserta autointerseção), ST_Area(::geography).
   Recusa (400): linha, vazia, área zero, > 100.000 ha, ponto > 4 ha ou sem área declarada.
5. INSERT da fazenda como pendente + flush.
6. NA MESMA TRANSAÇÃO: verificar_fazenda() em services/verificacao.py:
   - existe PRODES com ano > 2020? Se não -> 503, nada salvo (nunca um "apta" falso).
   - POLÍGONO: soma em m² da interseção com desmatamento pós-2020:
         SELECT COALESCE(SUM(ST_Area(ST_Intersection(f.geom, d.geom)::geography)), 0)
         FROM fazenda f JOIN camada_prodes d ON ST_Intersects(f.geom, d.geom)
         WHERE f.id = :id AND d.ano > :corte
     >= 1.000 m² (TOLERANCIA_M2) -> bloqueada; menor -> apta (área fica registrada).
     ::geography é obrigatório: sem ele a área sai em GRAUS², não em m².
   - PONTO: binário. Dentro de área desmatada -> bloqueada.
7. UPDATE status, area_sobreposta_m2, verificada_em, camada_versao_id -> COMMIT único (tudo ou nada = R1).
8. Resposta 201 com status; o site abre o detalhe verde (APTA) ou vermelho (BLOQUEADA).

Por que tolerância? Traço impreciso na borda gera sobreposição pequena sem significado.
Importação GeoJSON: lê cod_imovel, municipio, num_area (nomes do SICAR); tudo ou nada.
Adotar imóvel do CAR: o desenho é COPIADO para a fazenda, que passa a ter vida própria.
"""),

    Topico("Fluxo: embarque, fechamento e dossiê", ["embarque", "fechar", "fechamento", "dossie", "r2", "r3", "retrato"], """
Compor:
1. POST /embarques -> nasce RASCUNHO.
2. PUT /embarques/{id}/parcelas -> kg por fazenda. Cada fazenda precisa estar apta; senão 400 nomeando-a (R2).
   O site desabilita as bloqueadas, mas QUEM MANDA É O SERVIDOR (burlar a tela não adianta).
   Também recusa fazenda repetida, de outra conta, kg <= 0.

Fechar (POST /embarques/{id}/fechar):
1. Trava a linha (SELECT ... FOR UPDATE): dois cliques simultâneos não fecham duas vezes.
2. É da conta? senão 404. É rascunho? senão 409. Tem parcela? senão 400.
3. Todas continuam aptas? senão 400. (Revalida porque uma carga nova pode ter bloqueado alguma desde a composição.)
4. montar_retrato(): copia geometrias, CAR, status, área sobreposta, versão da camada, kg, documentos com SHA-256.
5. montar_geojson() e montar_pdf() (ReportLab) -> arquivos.salvar() (Blob em produção, disco em dev).
6. INSERT dossie (retrato JSONB), status = fechado, fechado_em = agora, COMMIT -> 200 com dossie_id.
7. Falhou no meio? ROLLBACK e apaga os arquivos já gravados.

Por que copiar (retrato) e não apontar (chave estrangeira)? Se o INPE publicar mapa novo e a fazenda virar bloqueada,
o dossiê antigo precisa continuar mostrando o que se sabia no dia do embarque. Registro que muda sozinho não é prova
(R3). Embarque fechado e dossiê são IMUTÁVEIS.

GeoJSON = para o sistema do importador (máquina lê). PDF = para leitura humana.
Limitação do PDF: decimais misturam ponto e vírgula; horários em UTC sem indicar fuso; fontes não embutidas.
"""),

    Topico("Fluxo: mapa e reprocessamento", ["mapa", "zoom", "calor", "reprocessar", "leaflet", "cache"], """
O mapa NÃO baixa o Brasil inteiro (863 mil polígonos). Comportamento por zoom:
- 0 a 6: mapa de calor nível 0, células de 0,25° (~28 km), uma resposta p/ o país (GET /camada/prodes/calor?nivel=0)
- 7 a 9: calor nível 1, células de 0,05° (~5,5 km), só o recorte visível
- 10+: polígonos reais do PRODES hachurados (GET /camada/prodes?bbox=...&v=versão), recorte arredondado em grade
  de 0,25° para reaproveitar resposta, até 3.000 feições simplificadas (ST_SimplifyPreserveTopology)
- 12+ com chip "Imóveis CAR": contornos cinza do CAR (GET /imoveis?bbox=...), só referência até adotar

GET /camada/versao (uma vez por sessão): o número da carga vai na URL (&v=); carga nova = URL nova = navegador não
usa a camada velha do cache (Cache-Control 1 h).

Cores: verde = apta, vermelho = bloqueada, cinza tracejado = pendente; ponto = círculo com anel tracejado.
Mapas de fundo: claro (Esri), ruas (OSM), satélite. Botão "Supressão PRODES" liga/desliga a camada.

Reprocessar: carga nova -> botão "Reprocessar camada" -> POST /fazendas/reverificar -> verifica todas as fazendas da
conta e lista as que mudaram de cor. Dossiês fechados NÃO mudam.
"""),

    Topico("Por que X e não Y (decisões)", ["decisoes", "porque", "escolhas", "tecnologias", "stack"], """
- PostgreSQL + PostGIS (e não calcular em Python): a pergunta é "este desenho cruza algum dos 863 mil, e quanto?".
  O índice espacial GiST vai direto aos candidatos próximos (como índice de livro). ~0,1 s por fazenda. Em Python a
  Function teria de carregar a camada inteira na memória.
- Azure Functions Flex Consumption (e não App Service): o plano gratuito do App Service estourava a cota. No Flex
  paga-se por execução, com cota grátis. Preço: cold start (primeira chamada após parado leva segundos).
  function_app.py embrulha o MESMO FastAPI (func.AsgiFunctionApp); host.json routePrefix "" (sem /api).
- FastAPI + Pydantic: validação declarativa e documentação OpenAPI automática em /docs.
- React 18 + TypeScript + Vite + Tailwind: componentes, tipagem, build estático (cabe no SWA grátis).
- Leaflet + React-Leaflet: mapas sem chave paga. Editor de geometria PRÓPRIO porque leaflet-draw está abandonado e
  quebra em ESM.
- React Query: cache de 5 min e sem refetch ao focar -> menos chamadas = menos execuções pagas. Sem polling.
- Blob (e não disco da API): instância da Function é temporária e pode haver várias. Acesso por identidade
  gerenciada (Storage Blob Data Contributor), sem chave guardada. services/arquivos.py: BackendDisco (dev/testes) e
  BackendBlob (produção), escolhido por STORAGE_BACKEND.
- JWT próprio (e não Entra ID): conta de estudante não registra apps; um login por exportador.
- Retrato JSONB (e não só FKs): prova congelada (R3).
- Alembic: esquema só muda por migrações (0001_baseline, 0002_imoveis, 0003_prodes_calor); banco local = Azure.
- Site chamando a Function direto (VITE_API_URL): SWA Free não vincula Function como back-end (só no Standard).
- CORS só na plataforma da Function (az functionapp cors add), CORS_ORIGENS vazio no FastAPI: no Flex a plataforma
  já responde o preflight; configurar nos dois duplica o cabeçalho e o navegador recusa.
- GitHub -> Azure por OIDC (identidade com credencial federada): nenhuma senha guardada.
"""),

    Topico("A API por dentro", ["api", "backend", "routers", "services", "fastapi", "endpoints"], """
A API é o ÚNICO PORTEIRO: só ela fala com o banco e com o Blob.

Três andares (backend/app/):
1. routers/ (balcões): auth, fornecedores, fazendas, documentos, embarques, dossies, camada, imoveis. Recebem o
   pedido, descobrem o usuário, chamam serviços, escolhem o código de resposta. Registrados em main.py com
   app.include_router(...).
2. services/ (inteligência): geometria.py (valida/repara), verificacao.py (PRODES), dossie.py (retrato, GeoJSON,
   PDF), arquivos.py (disco ou Blob). Criar, editar, importar e reprocessar chamam a MESMA verificar_fazenda().
3. models.py (tabelas ORM, restrições, índices) e schemas.py (Pydantic: formato de entrada/saída; valida CPF/CNPJ
   com _cpf_valido/_cnpj_valido, senha 8-72).

Dependências comuns: get_db() (sessão por requisição, database.py) e usuario_atual() (auth.py).
config.py (pydantic-settings): DATABASE_URL, JWT_SECRET, TOLERANCIA_M2, ano de corte, STORAGE_BACKEND,
BLOB_ACCOUNT_URL, limite de upload, DB_POOL_SIZE, DB_MAX_OVERFLOW, CORS_ORIGENS.
Versão da API no /docs: 0.3.0.
"""),

    Topico("Banco: camadas x tabelas mutáveis", ["banco", "tabelas", "mutaveis", "camada", "referencia", "modelo"], """
PostgreSQL 16 + PostGIS. SRID 4326 (WGS84) em toda geometria. Duas famílias:

FAMÍLIA 1 - dados de cada exportador (TABELAS MUTÁVEIS): mudam o tempo todo pelo uso do site, SEMPRE via API, e
cada linha tem dono (usuario_id). usuario, fornecedor, fazenda, documento, embarque, parcela, dossie.
Exceção: dossie mora aqui mas é IMUTÁVEL (escrito uma vez no fechamento). Embarque fechado também trava.

FAMÍLIA 2 - CAMADAS DE REFERÊNCIA: mapa oficial transformado em tabela. Comuns a todos, ninguém edita pelo site,
só mudam por script de carga. camada_versao (carimbo de cada carga), camada_prodes (~863 mil polígonos, 735 MB,
quase todo o banco), prodes_calor (resumo derivado p/ mapa de calor, recalculado após cada carga),
imovel_versao e imovel (base do CAR).

Analogia: tabelas mutáveis = caderno de trabalho da empresa. Camadas = livro de referência da biblioteca; só a
bibliotecária troca o livro.

Proteções do PRÓPRIO banco (além da API):
- FK composta (fornecedor_id, usuario_id): fazenda não aponta p/ fornecedor de outra conta
- ON DELETE RESTRICT em parcela.fazenda_id: não apaga fazenda usada em embarque
- UNIQUE: e-mail; CAR por conta; CPF/CNPJ por conta; identificação do embarque por conta; dossiê por embarque;
  cod_imovel
- CHECK: status válidos, quantidade_kg > 0, documento com exatamente um dono
- índices GiST em fazenda.geom, camada_prodes.geom, imovel.geom

Carga do PRODES (carga_prodes.py): lê .zip/shapefile do TerraBrasilis, converte SIRGAS 2000 -> WGS84, filtra
DESMATAMENTO, ano > 2020 e UF (aceita sigla OU nome por extenso; antes só sigla e perdia o Cerrado mineiro: 49 de
48.749 polígonos), cria camada_versao, recalcula prodes_calor. Carga do CAR (carga_imoveis.py): em lotes, upsert
por cod_imovel, repete lote se a conexão cair.
Seed: conta demo, 2 fornecedores, 4 fazendas em Adamantina/SP (3 aptas, 1 bloqueada), EMB-DEMO-001 rascunho;
seed_imoveis: PE, MA, RS (2 aptas + 1 bloqueada cada), EMB-DEMO-002.
"""),

    Topico("Quem pode mexer no banco e como", ["quem", "permissao", "acesso", "carga", "eudradmin", "firewall"], """
- Usuário do site: nunca toca no banco; pede à API; só vê/altera linhas da própria conta.
- API: escreve nas tabelas mutáveis. Local = usuário eudr. Azure = administrador eudradmin.
  (Resposta honesta se perguntarem de menor privilégio: um usuário de banco só p/ a aplicação seria melhoria.)
- carga: scripts de carga; só as 5 tabelas de camada; não enxerga cadastros (test_papel_carga.py confere).
- Administradora (eudradmin): migrações (alembic upgrade head). Na Azure, À MÃO e ANTES do merge, porque o runner
  do GitHub não tem IP fixo p/ o firewall -> toda migração precisa ser compatível com o código anterior.
- Barreiras: firewall nega tudo exceto serviços Azure + IPs liberados; SSL (sslmode=require); senhas só em .env,
  .env.azure (permissão 600) e App Settings; backup diário 7 dias; restaurar cria servidor novo.
"""),

    Topico("Segurança", ["seguranca", "segredos", "cors", "upload", "sha256", "403", "oidc"], """
- Senhas: bcrypt. Token: JWT HS256 8 h. Isolamento: filtro usuario_id + 404 (R6). Um único perfil (sem papéis).
- 401 x 403: 401 = não autenticado (sem token/vencido/adulterado). 403 NÃO é usado: recurso alheio -> 404, pois 403
  confirmaria que existe. Testes: test_sem_token_da_401, test_isolamento_entre_usuarios,
  test_documento_de_outro_usuario_da_404, test_dossie_de_outro_usuario_da_404.
- Segredos: nada no git (.gitignore: .env, .env.azure, local.settings.json). Produção: App Settings da Function
  (DATABASE_URL, JWT_SECRET, TOLERANCIA_M2, STORAGE_BACKEND, BLOB_ACCOUNT_URL, BLOB_CONTAINER, DB_POOL_SIZE,
  DB_MAX_OVERFLOW, CORS_ORIGENS vazio). GitHub environment production: AZURE_CLIENT_ID, AZURE_TENANT_ID,
  AZURE_SUBSCRIPTION_ID, AZURE_STATIC_WEB_APPS_API_TOKEN. Variáveis do repo: AZURE_FUNCTIONAPP_NAME, VITE_API_URL.
  Gerados com openssl rand. Sem Key Vault.
- HTTPS em tudo; Storage exige TLS 1.2; banco exige SSL.
- CORS: na Azure só na plataforma da Function; local CORSMiddleware p/ localhost:5173, preflight cache 2 h.
- Uploads: tipo pelos primeiros bytes (PDF/PNG/JPEG), 10 MB, nome reduzido ao nome base (não escapa da pasta),
  nome aleatório UUID no storage, contêiner privado. SHA-256 de cada documento vai p/ o dossiê.
- Entrada validada por Pydantic; geometria reparada/recusada no PostGIS.
- Concorrência: SELECT ... FOR UPDATE ao compor e fechar embarque.
"""),

    Topico("CI/CD e operação", ["cicd", "pipeline", "actions", "deploy", "smoke", "monitoramento", "backup", "custo"], """
Fluxo: branch a partir da main -> commits "tipo: descrição" (feat/fix/docs/infra) -> PR -> checks obrigatórios
"backend / testes" e "frontend / build" -> 1 aprovação, branch atualizada, sem force push -> merge.
PRs integrados: #1 a #5.

backend.yml: job testes sobe postgis/postgis:16-3.4, remove extensões que a Azure não tem (postgis_tiger_geocoder,
postgis_topology, fuzzystrmatch), pytest, alembic upgrade head + alembic check. Job deploy só na main, needs: testes,
environment production, azure/login por OIDC, Azure/functions-action (remote build, Flex, .funcignore), smoke test
/health/db até 20x a cada 15 s.
frontend.yml: npm ci, npm run build (tsc -b). Na main confere VITE_API_URL (falha se vazia p/ não publicar site
apontando p/ localhost), guarda dist/ como artefato 7 dias, publica com Azure/static-web-apps-deploy + token.
Gatilhos: PR sempre (sem filtro de pasta, pois são checks obrigatórios); push na main só da pasta que mudou;
workflow_dispatch; cancela execuções antigas do mesmo PR.
Duas barreiras contra deploy com defeito: checks no PR + deploy depende do job testes.

SITUAÇÃO REAL: as 10 execuções do backend na main falharam; as 3 últimas (14-15/11) passam nos testes e falham no
smoke test após ~7 min, embora a API responda /health/db = reachable. Causa não identificada (logs exigem login).
Frontend publica normalmente.

Operação: /health e /health/db; timeout 3m30s; Application Insights com amostragem (requests excluídas). Sem monitor
periódico (custaria execuções). Alerta de orçamento US$ 50 recomendado. Rollback = reverter commit por PR (novo
deploy) ou publicação manual (func azure functionapp publish / CLI do SWA) a partir de commit anterior. Custo:
zero a ~US$ 25/mês (banco). Desligar banco quando não usar (site abre, login falha).
"""),

    Topico("Testes", ["testes", "pytest", "validacao", "qualidade"], """
pytest em backend/tests/ contra PostGIS REAL (não simulado), porque a corretude depende das funções espaciais.
conftest.py recria eudr_test e aplica migrações uma vez por sessão; esvazia tabelas antes de cada teste;
TestClient faz requisições HTTP reais. Camadas sintéticas com áreas conhecidas -> valores exatos.
Fixtures: client, auth (usuária A), auth_b (usuária B).
106 funções, 13 arquivos, 112 casos; 112 passaram em 53 s (15/11/2026); alembic check sem diferenças; build ok
(aviso de pacote JS > 500 kB).
Arquivos: test_verificacao (21), test_embarques (12), test_documentos (7), test_arquivos_blob (6),
test_carga_prodes (15), test_carga_imoveis (12), test_camada (6), test_calor (7), test_imoveis (5),
test_functions (7), test_papel_carga (3), test_pool (1), test_seed_imoveis (4).
Defeitos que viraram teste: test_uf_por_sigla_ou_por_nome_por_extenso; test_versao_da_camada_muda_a_cada_carga
(cache velho do mapa, commit d064715); test_queda_de_conexao_no_meio_repete_o_lote (commit fb4a80e).
Front-end SEM testes automatizados (só typecheck/build + teste manual). Validação = roteiro de demonstração do
context.md: desenhar sobre desmatamento -> bloqueio -> recusa no embarque -> incluir aptas -> fechar -> baixar.
"""),

    Topico("Front-end por dentro", ["frontend", "react", "paginas", "componentes", "api.ts", "consultas"], """
main.tsx: QueryClient (staleTime 5 min, sem refetch ao focar), BrowserRouter, AuthProvider.
App.tsx: /login pública; demais dentro de Protegida (sem token -> /login; com token -> Layout com menu).
Rotas: /fazendas, /fazendas/nova, /fazendas/:id, /fornecedores, /fornecedores/:id, /embarques, /embarques/:id,
/dossies, /dossies/:id.
Componentes: fazendas-board.tsx (lista + mapa), fazendas-board-utils/mapa.tsx (camadas), editor-geometria.tsx
(desenho próprio), documentos.tsx, layout.tsx (array NAVEGACAO), comum.tsx (Painel, CabecalhoPagina, Mensagem,
Carregando, Campo, Dado, StatusPill).
lib/api.ts: ÚNICO ponto de fetch; base = VITE_API_URL (local http://localhost:8000); põe Bearer; 401 -> apaga token
+ evento de sessão expirada; falha de rede -> ApiErro status 0 "Não foi possível falar com o servidor..."; mostra
detail da API em português; 422 vira texto legível; api.baixar() p/ downloads com token (blob + Content-Disposition).
lib/consultas.ts: hooks React Query (useFazendas, useEmbarque, useDossie...); useInvalidarCadastro() invalida
fazendas, fornecedores e embarques juntos; dossiê staleTime Infinity; retry até 2x só p/ não-4xx (cobre cold start).
lib/status.ts: cores; lib/tipos.ts: interfaces espelho dos schemas da API.
"""),

    Topico("Como adicionar uma página e um endpoint", ["adicionar", "novo", "endpoint", "pagina", "evoluir", "futuro", "como fazer"], """
Ordem: banco (se precisar) -> API -> site. Exemplo hipotético: página "Resumo" (contagem de aptas/bloqueadas/pendentes
e embarques em rascunho). Não existe no projeto; serve de molde.

PASSO 0 - mudar o banco? (só se for guardar algo novo)
  editar models.py -> alembic revision --autogenerate -m "..." -> CONFERIR o arquivo -> alembic upgrade head ->
  alembic check. Na Azure: aplicar à mão ANTES do merge; preferir colunas que aceitam vazio (compatível c/ código
  antigo). Se for tabela de camada: GRANT ao usuário carga em infra/papel-carga.sql.

PASSO 1 - backend
  1a. schemas.py:
        class ResumoOut(BaseModel):
            aptas: int
            bloqueadas: int
            pendentes: int
            embarques_em_rascunho: int
  1b. routers/resumo.py:
        router = APIRouter(prefix="/resumo", tags=["resumo"])
        @router.get("", response_model=ResumoOut)
        def obter(db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
            por_status = dict(db.execute(
                select(Fazenda.status, func.count())
                .where(Fazenda.usuario_id == usuario.id)      # R6 OBRIGATÓRIO
                .group_by(Fazenda.status)).all())
            rascunhos = db.scalar(select(func.count()).select_from(Embarque)
                .where(Embarque.usuario_id == usuario.id, Embarque.status == "rascunho"))
            return ResumoOut(aptas=por_status.get("apta", 0), bloqueadas=por_status.get("bloqueada", 0),
                             pendentes=por_status.get("pendente", 0), embarques_em_rascunho=rascunhos or 0)
  1c. main.py: importar resumo e app.include_router(resumo.router)   (sem isso -> 404)
  1d. tests/test_resumo.py:
        def test_resumo_vazio(client, auth):
            r = client.get("/resumo", headers=auth)
            assert r.status_code == 200
        def test_resumo_exige_login(client):
            assert client.get("/resumo").status_code == 401
      + teste de isolamento: criar fazenda com auth, conferir que auth_b continua zerado.
      Rodar: python -m pytest tests -q. Testar manual em http://localhost:8000/docs (botão Authorize).

PASSO 2 - frontend
  2a. lib/tipos.ts: export interface Resumo { aptas: number; bloqueadas: number; pendentes: number;
      embarques_em_rascunho: number }   (mesmos nomes do ResumoOut = o "contrato")
  2b. lib/consultas.ts: chaves.resumo = ["resumo"];
        export const useResumo = () =>
          useQuery({ queryKey: chaves.resumo, queryFn: () => api.get<Resumo>("/resumo") });
      e incluir chaves.resumo em useInvalidarCadastro() (senão número velho por até 5 min).
  2c. pages/resumo.tsx: usa useResumo() + CabecalhoPagina, Mensagem (erro), Carregando, Painel.
  2d. App.tsx: import PaginaResumo; <Route path="/resumo" element={<PaginaResumo />} /> DENTRO de Protegida.
  2e. layout.tsx: { para: "/resumo", rotulo: "Resumo", icone: LayoutDashboard } no array NAVEGACAO.
  Rodar npm run dev; antes do PR npm run build (checa tipos).

GRAVAR (POST/PUT/DELETE) no front: useMutation({ mutationFn: (corpo) => api.put(...), onSuccess: () => invalidar() }).
No back: schema ...In, buscar recurso FILTRANDO pela conta (ver obter_fornecedor), alterar, db.commit();
regra violada -> raise HTTPException(400 ou 409, detail="mensagem em português") (o api.ts mostra na tela).

COMO AS PONTAS SE ENCONTRAM: endereço VITE_API_URL + rota; contrato = schema Python <-> interface TS; login
automático (api.ts manda token, usuario_atual confere); CORS não muda p/ rota nova (é por origem); deploy: branch ->
PR -> merge -> workflow da pasta publica.

ERROS COMUNS: 404 = faltou include_router ou caminho diferente do prefix; 401 = sem token; 422 = corpo fora do
schema; dados de outra conta = faltou filtro usuario_id; tela desatualizada = faltou invalidar chave; rota fixa
(/fazendas/exportar) engolida = declarar ANTES de /fazendas/{fazenda_id}; PR vermelho no alembic check = mudou
models.py sem migração.
"""),

    Topico("Limitações e perguntas prováveis", ["limitacoes", "banca", "perguntas", "fraquezas"], """
LIMITAÇÕES:
- deploy automático do backend falha no smoke test (10 execuções na main); causa não identificada
- Amazônia só com PRODES preliminar 2026; sem histórico 2021-2025 -> desmatamento desses anos na Amazônia não bloqueia
- só PRODES; não comparado com o mapa de cobertura florestal 2020 do JRC (referência do lado europeu)
- sem balanço de massa (registra kg por fazenda, não mistura de lotes)
- conta única por empresa: sem perfis, usuários individuais, trilha de auditoria
- sem recuperação de senha; sem limite de tentativas de login; token no localStorage (risco XSS)
- front sem testes automatizados; func start local não testado
- React Router 6 com 2 alertas moderados (resolvem só na v7); pacote JS > 500 kB; cold start
- PDF: decimais mistos, horário UTC sem fuso, fontes não embutidas

PERGUNTAS PROVÁVEIS:
- Por que 1.000 m²? Imprecisão de borda; configurável; área registrada mesmo sem bloquear.
- E se o INPE atualizar? Carga nova + Reprocessar; fazendas mudam de cor; dossiês antigos não.
- O que impede fazenda bloqueada no embarque? O servidor, ao compor e de novo ao fechar.
- Como uma empresa não vê a outra? Filtro usuario_id do token + 404 p/ recurso alheio.
- Por que não 403? Confirmaria que o recurso existe em outra conta.
- Por que Functions? Cota do App Service; paga por execução; custo = cold start.
- Por que PostGIS? Índice GiST; ~0,1 s; não carregar 863 mil polígonos na API.
- Continuidade: corrigir smoke test -> histórico Amazônia -> validar com exportador real -> perfis/recuperação de
  senha/auditoria -> Ibama/TI/UC -> comparar com JRC -> balanço de massa.
"""),
]


# =====================================================================================================
# 3. PROVA
# =====================================================================================================

@dataclass
class Questao:
    enunciado: str
    alternativas: List[str]
    correta: int  # índice (0 = a)
    explicacao: str


PROVA: List[Questao] = [
    Questao("Usuária salva fazenda sem camada PRODES carregada. O que a API faz?",
            ["Salva como apta", "Salva como pendente e verifica depois", "Recusa com 503 e não salva nada",
             "Salva como bloqueada"], 2,
            "R1: sem camada -> 503, transação não grava. Apta falso seria o pior erro."),
    Questao("Quando um polígono fica bloqueado?",
            ["Encostou em qualquer PRODES de qualquer ano", "Sobreposição >= 1.000 m² com desmatamento de ano > 2020",
             "Mais de 10% sobre desmatamento", "CAR cancelado no SICAR"], 1,
            "Soma da interseção >= TOLERANCIA_M2 (R5)."),
    Questao("Regra para ponto?",
            ["Qualquer tamanho; bloqueia a menos de 1 km", "Até 4 ha; bloqueia se cair dentro de área desmatada",
             "Até 4 ha; tolerância de 1.000 m²", "Pontos não são aceitos"], 1,
            "R4: ponto não tem área; critério binário."),
    Questao("GET /fazendas/8 de outra empresa responde:",
            ["403", "401", "404, para não revelar que existe", "200"], 2, "R6."),
    Questao("Por que o dossiê guarda retrato JSONB?",
            ["Ocupa menos espaço", "Continua mostrando o que se sabia no fechamento", "PostgreSQL proíbe FK",
             "Front carrega mais rápido"], 1, "R3: prova congelada."),
    Questao("Por que verificar no PostGIS e não em Python?",
            ["Python não calcula área", "GiST acha só os próximos sem carregar a camada na memória",
             "Azure proíbe geoprocessamento", "Só PostGIS lê GeoJSON"], 1, "~0,1 s por fazenda."),
    Questao("Para que serve ::geography em ST_Area?",
            ["Converter p/ SIRGAS", "Área em m² e não graus²", "Usar o índice", "Corrigir autointerseção"], 1,
            "SRID 4326 em geometry dá graus²."),
    Questao("Por que Functions Flex e não App Service?",
            ["FastAPI não roda no App Service", "Cota do App Service gratuito estourava; Flex paga por execução",
             "Functions não tem cold start", "SWA exige Functions"], 1, "Custo: cold start."),
    Questao("O que o usuário carga pode fazer?",
            ["Tudo", "Só ler/gravar tabelas de camada", "Ler cadastros", "Rodar Alembic"], 1, "Menor privilégio."),
    Questao("Para que serve prodes_calor?",
            ["Histórico de verificações", "Resumo em células p/ mapa de calor afastado", "Temperatura dos biomas",
             "Polígonos originais"], 1, "Derivada, recalculada após carga."),
    Questao("Por que arquivos no Blob e não no disco da API?",
            ["Instância temporária e pode haver várias", "Disco é mais caro", "Postgres não guarda arquivo",
             "Blob gera PDF"], 0, "Persistência e compartilhamento."),
    Questao("Como o GitHub publica sem senha da Azure?",
            ["Senha nos secrets", "OIDC + identidade gerenciada com credencial federada", "JWT do OrigemCheck",
             "Sempre manual"], 1, "Só aceita o environment production deste repo."),
    Questao("Por que migração na Azure é aplicada à mão antes do merge?",
            ["Alembic não roda na Azure", "Runner do GitHub sem IP fixo p/ o firewall", "Regra da disciplina",
             "Azure sem PostGIS"], 1, "Migração precisa ser compatível com o código anterior."),
    Questao("Por que o fechamento revalida as fazendas?",
            ["Redundância", "A camada pode ter mudado desde a composição", "Front perdeu dados", "Somar kg"], 1, "R2."),
    Questao("Criou routers/resumo.py e GET /resumo dá 404. Causa provável?",
            ["Faltou include_router no main.py", "Faltou alembic upgrade", "Token vencido", "CORS"], 0,
            "Token vencido daria 401."),
]


# =====================================================================================================
# 4. FUNÇÕES
# =====================================================================================================

def _formatar(texto: str) -> str:
    saida = []
    for linha in textwrap.dedent(texto).strip("\n").splitlines():
        if not linha.strip() or linha.startswith(" "):
            saida.append(linha)
            continue
        recuo = "  " if linha.lstrip().startswith(("- ", "1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.")) else ""
        saida.append(textwrap.fill(linha, LARGURA, subsequent_indent=recuo + "  " if recuo else ""))
    return "\n".join(saida)


def _cabecalho(titulo: str) -> str:
    return f"\n{'=' * LARGURA}\n{titulo.upper()}\n{'=' * LARGURA}"


def listar() -> None:
    print(_cabecalho("OrigemCheck - tópicos"))
    for i, t in enumerate(TOPICOS, 1):
        print(f"{i:>3}. {t.titulo}   [{', '.join(t.apelidos[:4])}]")
    print("\nReferência rápida: tabelas, endpoints, status, regras, azure, numeros, comandos, quem, projeto")
    print("Outros: buscar <termo> | prova | tudo")


def mostrar(t: Topico) -> None:
    print(_cabecalho(t.titulo))
    print(_formatar(t.texto))


def _referencia(nome: str) -> bool:
    blocos = {
        "projeto": PROJETO, "regras": REGRAS_DE_NEGOCIO, "azure": RECURSOS_AZURE, "numeros": NUMEROS,
        "comandos": COMANDOS, "quem": QUEM_MEXE_NO_BANCO,
        "status": {str(k): v for k, v in STATUS_HTTP.items()},
        "tabelas": {k: f"[{a}] {b}" for k, (a, b) in TABELAS.items()},
    }
    if nome == "endpoints":
        print(_cabecalho("endpoints"))
        for metodo, rota, desc in ENDPOINTS:
            print(textwrap.fill(f"{metodo:<15} {rota:<38} {desc}", LARGURA, subsequent_indent=" " * 55))
        return True
    if nome in blocos:
        print(_cabecalho(nome))
        for k, v in blocos[nome].items():
            print(textwrap.fill(f"{k}: {v}", LARGURA, subsequent_indent="    "))
        return True
    return False


def _todas_as_linhas():
    for t in TOPICOS:
        for linha in textwrap.dedent(t.texto).splitlines():
            yield t.titulo, linha
    for nome, bloco in (("projeto", PROJETO), ("regras", REGRAS_DE_NEGOCIO), ("azure", RECURSOS_AZURE),
                        ("numeros", NUMEROS), ("comandos", COMANDOS), ("quem", QUEM_MEXE_NO_BANCO)):
        for k, v in bloco.items():
            yield nome, f"{k}: {v}"
    for k, v in STATUS_HTTP.items():
        yield "status", f"{k}: {v}"
    for k, (a, b) in TABELAS.items():
        yield "tabelas", f"{k} [{a}]: {b}"
    for m, r, d in ENDPOINTS:
        yield "endpoints", f"{m} {r} - {d}"


def _sem_acento(s: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


def buscar(termo: str) -> None:
    alvo = _sem_acento(termo)
    achados = [(onde, l.strip()) for onde, l in _todas_as_linhas() if alvo in _sem_acento(l)]
    print(_cabecalho(f'busca: "{termo}" ({len(achados)} resultados)'))
    for onde, linha in achados:
        print(textwrap.fill(f"[{onde}] {linha}", LARGURA, subsequent_indent="    "))


def prova() -> None:
    questoes = PROVA[:]
    random.shuffle(questoes)
    acertos = 0
    for n, q in enumerate(questoes, 1):
        print(f"\n{n}/{len(questoes)}. {q.enunciado}")
        for i, alt in enumerate(q.alternativas):
            print(f"   {'abcd'[i]}) {alt}")
        resp = ""
        while resp not in ("a", "b", "c", "d"):
            try:
                resp = input("Resposta (a-d): ").strip().lower()
            except EOFError:
                return
        if "abcd".index(resp) == q.correta:
            acertos += 1
            print("   Certo. " + q.explicacao)
        else:
            print(f"   Errado: a correta é {'abcd'[q.correta]}) {q.alternativas[q.correta]}. {q.explicacao}")
    print(f"\nResultado: {acertos}/{len(questoes)}")


def main(args: List[str]) -> None:
    if not args:
        listar(); return
    cmd = args[0].lower()
    if cmd == "tudo":
        for t in TOPICOS:
            mostrar(t)
        for nome in ("projeto", "regras", "status", "endpoints", "tabelas", "quem", "azure", "numeros", "comandos"):
            _referencia(nome)
        return
    if cmd == "prova":
        prova(); return
    if cmd == "buscar":
        buscar(" ".join(args[1:])); return
    if _referencia(cmd):
        return
    if cmd.isdigit() and 1 <= int(cmd) <= len(TOPICOS):
        mostrar(TOPICOS[int(cmd) - 1]); return
    termo = _sem_acento(" ".join(args))
    candidatos = [t for t in TOPICOS if termo in _sem_acento(t.titulo) or any(termo in _sem_acento(a) for a in t.apelidos)]
    if candidatos:
        for t in candidatos:
            mostrar(t)
    else:
        buscar(" ".join(args))


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # acentos certos também no terminal do Windows
    except (AttributeError, ValueError):
        pass
    try:
        main(sys.argv[1:])
    except (BrokenPipeError, KeyboardInterrupt):
        pass
