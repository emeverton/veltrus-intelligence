from fastapi import APIRouter

router = APIRouter()


@router.post("/run")
async def run_agent():
    return {"status": "not_implemented", "layer": "agents"}


@router.get("/status/{run_id}")
async def get_run_status(run_id: str):
    return {"status": "not_implemented", "run_id": run_id, "layer": "agents"}
