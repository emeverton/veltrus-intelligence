from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    debug: bool = False
    anthropic_api_key: str
    database_url: str
    qdrant_host: str = "intelligence_qdrant"
    qdrant_port: int = 6333
    nats_url: str = "nats://intelligence_nats:4222"
    attribution_worker_enabled: bool = True
    graph_db_url: str = "postgresql://graphuser:changeme@intelligence_graphdb:5432/revenue_graph"
    vastai_api_key: str = ""
    vastai_offer_id: int = 0
    hf_token: str = ""
    gpu_inference_image: str = "veltrus-intelligence-gpu:latest"
    gpu_llm_base_url: str = ""
    shopify_webhook_secret: str = ""

    class Config:
        env_file = ".env"


settings = Settings()
