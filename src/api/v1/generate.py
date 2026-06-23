from fastapi import APIRouter

router = APIRouter()


@router.post("/creative")
async def generate_creative():
    return {"status": "not_implemented", "layer": "generate"}


@router.post("/copy")
async def generate_copy():
    return {"status": "not_implemented", "layer": "generate"}
