from fastapi import APIRouter

from services.llm_service import provider_status
from services.web_search import is_configured as web_search_configured

router = APIRouter()


@router.get("/config")
def config():
    status = provider_status()
    status["web_search_configured"] = web_search_configured()
    return status
