"""
GPU Inference Server — roda no Vast.ai, NÃO no VPS.
"""
import base64
import io
import logging

import torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Veltrus GPU Inference", version="0.1.0")
logger = logging.getLogger(__name__)

_flux_pipe = None
_wan_pipe = None


def _get_flux():
    global _flux_pipe
    if _flux_pipe is None:
        from diffusers import FluxPipeline

        logger.info("Loading FLUX.1-schnell (~12GB VRAM)...")
        _flux_pipe = FluxPipeline.from_pretrained(
            "black-forest-labs/FLUX.1-schnell",
            torch_dtype=torch.bfloat16,
        ).to("cuda")
        logger.info("FLUX loaded.")
    return _flux_pipe


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "device": "cuda" if torch.cuda.is_available() else "cpu",
        "vram_free_gb": round(torch.cuda.mem_get_info()[0] / 1e9, 2)
        if torch.cuda.is_available()
        else None,
    }


class ImageRequest(BaseModel):
    prompt: str
    width: int = 768
    height: int = 768
    steps: int = 4
    guidance_scale: float = 0.0


@app.post("/generate/image")
async def generate_image(req: ImageRequest):
    """Gera imagem com FLUX.1-schnell. Retorna PNG em base64."""
    pipe = _get_flux()
    result = pipe(
        prompt=req.prompt,
        width=req.width,
        height=req.height,
        num_inference_steps=req.steps,
        guidance_scale=req.guidance_scale,
        output_type="pil",
    )
    image = result.images[0]

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    b64 = base64.b64encode(buffer.getvalue()).decode()

    return {
        "status": "ok",
        "format": "png",
        "width": image.width,
        "height": image.height,
        "data_base64": b64,
    }


class VideoRequest(BaseModel):
    prompt: str
    duration_seconds: float = 3.0
    fps: int = 16


@app.post("/generate/video")
async def generate_video(req: VideoRequest):
    """Gera vídeo com Wan 2.1 1.3B. Retorna MP4 em base64."""
    global _flux_pipe
    if _flux_pipe is not None:
        del _flux_pipe
        _flux_pipe = None
        torch.cuda.empty_cache()

    raise HTTPException(
        status_code=501,
        detail="Wan 2.1 não instalado. Adicionar wan2.1 ao requirements.txt do infra/gpu-inference.",
    )
