from fastapi import APIRouter

router = APIRouter()


@router.post("/resolve")
async def resolve_identity():
    return {"status": "not_implemented", "layer": "identity"}


@router.get("/profile/{identity_id}")
async def get_profile(identity_id: str):
    return {"status": "not_implemented", "identity_id": identity_id, "layer": "identity"}
