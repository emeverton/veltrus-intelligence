"""
Kokoro TTS — síntese de voz no VPS (CPU).
Modelo: kokoro-82m (ONNX, ~160MB RAM em inferência)
"""
import asyncio
import base64
import io
import logging
from functools import lru_cache

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_kokoro():
    """Carrega Kokoro ONNX uma vez."""
    try:
        from kokoro_onnx import Kokoro

        model = Kokoro("kokoro-v0_19.onnx", "voices.bin")
        logger.info("Kokoro TTS loaded (CPU)")
        return model
    except ImportError:
        logger.error("kokoro-onnx not installed. Add to requirements.txt.")
        return None
    except FileNotFoundError:
        logger.error("Kokoro model files not found. Download kokoro-v0_19.onnx + voices.bin")
        return None


def synthesize_sync(text: str, voice: str = "af", speed: float = 1.0) -> bytes:
    """
    Síntese síncrona. Retorna bytes de áudio WAV.
    voice: 'af' (female EN), 'am' (male EN)
    """
    model = _get_kokoro()
    if model is None:
        raise RuntimeError("Kokoro model not available")

    samples, sample_rate = model.create(text, voice=voice, speed=speed, lang="en-us")

    import soundfile as sf

    buffer = io.BytesIO()
    sf.write(buffer, samples, sample_rate, format="WAV")
    return buffer.getvalue()


async def synthesize_async(text: str, voice: str = "af", speed: float = 1.0) -> dict:
    """Wrapper async. Retorna WAV em base64."""
    wav_bytes = await asyncio.to_thread(synthesize_sync, text, voice, speed)
    return {
        "format": "wav",
        "voice": voice,
        "text_length": len(text),
        "data_base64": base64.b64encode(wav_bytes).decode(),
    }
