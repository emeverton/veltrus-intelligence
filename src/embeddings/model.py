import asyncio
import logging
from functools import lru_cache

from fastembed import TextEmbedding

logger = logging.getLogger(__name__)
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def _get_model() -> TextEmbedding:
    logger.info("Loading fastembed model: %s", MODEL_NAME)
    return TextEmbedding(model_name=MODEL_NAME)


def encode_text(text: str) -> list[float]:
    """
    Gera embedding 384-dim para um texto.
    Síncrono — usar via asyncio.to_thread() em código async.
    """
    model = _get_model()
    embeddings = list(model.embed([text]))
    return embeddings[0].tolist()


async def encode_text_async(text: str) -> list[float]:
    """Wrapper async para encode_text."""
    return await asyncio.to_thread(encode_text, text)


def warmup() -> None:
    """Precarregar o modelo no startup (evita latência no primeiro request)."""
    _get_model()
    encode_text("warmup")
    logger.info("fastembed model warmed up")
