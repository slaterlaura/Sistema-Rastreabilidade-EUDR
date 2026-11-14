-- Usuário de banco "carga": só consegue mexer nas camadas de referência (PRODES e imóveis do CAR).
-- Não lê nem altera contas, fornecedores, fazendas, documentos, embarques ou dossiês.
-- Rodar como administrador, uma vez (e de novo se novas tabelas de camada forem criadas).
-- A senha é definida à parte (ver docs/DEPLOY-AZURE.md, passo 9), para não ficar neste arquivo.

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'carga') THEN
        CREATE ROLE carga LOGIN;
    END IF;
    EXECUTE format('GRANT CONNECT, TEMPORARY ON DATABASE %I TO carga', current_database());
END $$;

GRANT USAGE ON SCHEMA public TO carga;

GRANT SELECT, INSERT, UPDATE, DELETE ON camada_versao, camada_prodes, imovel_versao, imovel TO carga;
GRANT USAGE, SELECT ON SEQUENCE camada_versao_id_seq, camada_prodes_id_seq, imovel_versao_id_seq, imovel_id_seq TO carga;
GRANT SELECT ON spatial_ref_sys, alembic_version TO carga;
