from fastapi import APIRouter

router = APIRouter()


@router.post("/attribute")
async def attribute_touchpoints():
    return {"status": "not_implemented", "layer": "attribution"}


@router.get("/models")
async def list_models():
    return {"status": "not_implemented", "layer": "attribution"}
