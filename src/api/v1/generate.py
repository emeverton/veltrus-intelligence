import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_session
from src.gpu.generate_client import generate_image as gpu_generate_image
from src.gpu.generate_client import gpu_health
from src.voice.kokoro import synthesize_async

router = APIRouter()


class ImageGenerateRequest(BaseModel):
    prompt: str
    width: int = 768
    height: int = 768


class VoiceGenerateRequest(BaseModel):
    text: str
    voice: str = "af"
    speed: float = 1.0


@router.get("/gpu/status")
async def get_gpu_status():
    """Status do servidor GPU Vast.ai."""
    from src.gpu.instance_manager import get_llm_url

    health = await gpu_health()
    health["llm_url_available"] = (await get_llm_url()) is not None
    return health


@router.post("/gpu/start")
async def start_gpu_instance():
    """
    Inicia uma instância GPU no Vast.ai.
    Aguarda até 5 minutos para ficar pronta.
    """
    from src.gpu.instance_manager import start_gpu

    return await start_gpu(wait_for_ready=True, timeout_seconds=300)


@router.post("/gpu/stop")
async def stop_gpu_instance():
    """Para e destrói a instância GPU. Interrompe cobranças imediatamente."""
    from src.gpu.instance_manager import stop_gpu

    return await stop_gpu()


@router.post("/image")
async def generate_image(
    payload: ImageGenerateRequest,
    session: AsyncSession = Depends(get_session),
):
    """
    Gera imagem via FLUX.1-schnell no GPU Vast.ai.
    Retorna imagem PNG em base64.
    """
    job_id = str(uuid.uuid4())
    try:
        result = await gpu_generate_image(
            prompt=payload.prompt,
            width=payload.width,
            height=payload.height,
        )
        await session.execute(
            sql_text("""
                INSERT INTO generation_jobs (id, job_type, prompt, status, result_data, gpu_used)
                VALUES (:id, 'image', :prompt, 'done', CAST(:result AS jsonb), true)
            """),
            {
                "id": job_id,
                "prompt": payload.prompt,
                "result": json.dumps(
                    {
                        "format": result.get("format"),
                        "dims": f"{result.get('width')}x{result.get('height')}",
                    }
                ),
            },
        )
        await session.commit()
        return {"job_id": job_id, "status": "done", **result}

    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e


@router.post("/voice")
async def synthesize_voice(
    payload: VoiceGenerateRequest,
    session: AsyncSession = Depends(get_session),
):
    """
    Sintetiza voz via Kokoro TTS (CPU — sempre disponível).
    Retorna áudio WAV em base64.
    """
    job_id = str(uuid.uuid4())
    result = await synthesize_async(payload.text, payload.voice, payload.speed)
    await session.execute(
        sql_text("""
            INSERT INTO generation_jobs (id, job_type, prompt, status, result_data, gpu_used)
            VALUES (:id, 'voice', :prompt, 'done', CAST(:result AS jsonb), false)
        """),
        {
            "id": job_id,
            "prompt": payload.text[:200],
            "result": json.dumps({"format": result["format"], "chars": result["text_length"]}),
        },
    )
    await session.commit()
    return {"job_id": job_id, "status": "done", **result}
