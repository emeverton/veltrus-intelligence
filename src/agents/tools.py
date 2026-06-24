TOOLS = [
    {
        "name": "query_revenue_by_channel",
        "description": (
            "Retorna revenue total atribuído por canal de marketing para um modelo de atribuição. "
            "Use para responder perguntas como 'qual canal gerou mais receita?' ou "
            "'compare Google Ads vs Meta Ads'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "model": {
                    "type": "string",
                    "enum": ["first_touch", "last_touch", "linear", "time_decay", "shapley"],
                    "description": "Modelo de atribuição. Use 'linear' como padrão.",
                },
                "limit": {
                    "type": "integer",
                    "default": 10,
                    "description": "Número máximo de canais a retornar.",
                },
            },
            "required": ["model"],
        },
    },
    {
        "name": "query_identity_ltv",
        "description": (
            "Retorna identidades com maior LTV (Life-Time Value) — soma de revenue de todas as conversões. "
            "Use para perguntas sobre top clientes, segmentação por valor ou análise de base."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "min_revenue": {
                    "type": "number",
                    "default": 0,
                    "description": "Filtro mínimo de revenue por conversão individual.",
                },
                "limit": {
                    "type": "integer",
                    "default": 10,
                },
            },
        },
    },
    {
        "name": "search_creatives",
        "description": (
            "Busca criativos similares por texto usando busca vetorial. "
            "Use para encontrar criativos sobre um tema, comparar variações ou "
            "identificar criativos de alto desempenho por similaridade semântica."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Texto descrevendo o criativo ou tema a buscar.",
                },
                "channel": {
                    "type": "string",
                    "description": "Filtrar por canal (opcional): google_ads, meta_ads, email, etc.",
                },
                "limit": {
                    "type": "integer",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "forecast_revenue",
        "description": (
            "Gera forecast de receita para os próximos N dias usando Prophet (Meta). "
            "Usa dados históricos de conversões do banco. "
            "Use para perguntas sobre projeções, tendências ou planejamento futuro."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "default": 30,
                    "description": "Número de dias a projetar (7, 14, 30, 60, 90).",
                },
                "channel": {
                    "type": "string",
                    "description": "Filtrar por canal de atribuição (opcional).",
                },
            },
        },
    },
    {
        "name": "get_attribution_report",
        "description": (
            "Retorna resultados de atribuição para um profile específico, mostrando "
            "como cada canal/campanha foi creditado pela conversão."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "profile_id": {
                    "type": "string",
                    "description": "UUID do perfil de identidade.",
                },
                "model": {
                    "type": "string",
                    "description": "Modelo de atribuição específico (opcional).",
                },
            },
            "required": ["profile_id"],
        },
    },
]
