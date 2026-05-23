from fastapi import APIRouter

from services.llm_service import provider_status

router = APIRouter()


@router.get("/config")
def config():
    return provider_status()
