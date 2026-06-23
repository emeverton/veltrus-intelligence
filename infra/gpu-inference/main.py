"""
GPU Inference Server — roda no Vast.ai, NÃO no VPS.
FLUX (8080) + Wan 2.1 video. vLLM/Qwen inicia via onstart na porta 8081.
"""
import asyncio
import base64
import io
import logging
import os
import tempfile

import torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Veltrus GPU Inference", version="0.2.0")
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


def _get_wan():
    global _wan_pipe, _flux_pipe
    if _wan_pipe is None:
        if _flux_pipe is not None:
            del _flux_pipe
            _flux_pipe = None
            torch.cuda.empty_cache()
        logger.info("Loading Wan 2.1 1.3B...")
        try:
            from wan.pipeline import WanPipeline
        except ImportError as exc:
            raise HTTPException(
                status_code=501,
                detail=f"Wan 2.1 não instalado: {exc}",
            ) from exc
        _wan_pipe = WanPipeline.from_pretrained(
            "Wan-AI/Wan2.1-T2V-1.3B",
            torch_dtype=torch.bfloat16,
        ).to("cuda")
        logger.info("Wan 2.1 loaded")
    return _wan_pipe


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
    pipe = await asyncio.to_thread(_get_flux)
    result = await asyncio.to_thread(
        pipe,
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


def _generate_video_sync(req: VideoRequest) -> dict:
    pipe = _get_wan()
    output = pipe(
        prompt=req.prompt,
        num_frames=int(req.fps * req.duration_seconds),
        height=480,
        width=832,
        guidance_scale=5.0,
        num_inference_steps=20,
    )
    frames = output.frames[0]

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        tmp_path = tmp.name

    import imageio

    imageio.mimwrite(
        tmp_path,
        [frame for frame in frames],
        fps=req.fps,
        codec="libx264",
    )

    with open(tmp_path, "rb") as f:
        video_bytes = f.read()
    os.unlink(tmp_path)

    return {
        "status": "ok",
        "format": "mp4",
        "frames": len(frames),
        "fps": req.fps,
        "data_base64": base64.b64encode(video_bytes).decode(),
    }


@app.post("/generate/video")
async def generate_video(req: VideoRequest):
    """Gera vídeo com Wan 2.1 1.3B. Retorna MP4 em base64."""
    try:
        return await asyncio.to_thread(_generate_video_sync, req)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Wan video generation failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
