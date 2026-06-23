-- Habilitar AGE
CREATE EXTENSION IF NOT EXISTS age;
LOAD 'age';
SET search_path = ag_catalog, "$user", public;

-- Criar grafo principal
SELECT create_graph('revenue_graph');

-- Verificar
SELECT * FROM ag_graph;
