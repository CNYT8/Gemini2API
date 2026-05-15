import logging
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core.gemini_client import gemini_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["Admin"])


class ReloadCookiesRequest(BaseModel):
    psid: Optional[str] = None
    psidts: Optional[str] = None


@router.post("/reload-cookies")
async def reload_cookies(req: ReloadCookiesRequest = None):
    if req and (req.psid or req.psidts):
        success = await gemini_client.reload_cookies(psid=req.psid, psidts=req.psidts)
    else:
        from app.config import Settings
        try:
            fresh = Settings()
            success = await gemini_client.reload_cookies(
                psid=fresh.gemini_psid,
                psidts=fresh.gemini_psidts,
            )
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"error": {"message": f"Failed to read .env: {e}", "type": "config_error"}},
            )

    if success:
        return {"status": "ok", "message": "Cookies reloaded successfully", "healthy": True}
    else:
        return JSONResponse(
            status_code=503,
            content={"error": {"message": "Cookie reload failed. Check if cookies are valid.", "type": "reload_error"}},
        )


@router.get("/status")
async def admin_status():
    return {
        "healthy": gemini_client.is_healthy,
        "models_count": len(gemini_client.models),
        "models": gemini_client.models[:10],
    }


@router.get("/check-account")
async def check_account():
    result = await gemini_client.check_account()
    return result


@router.get("/health-history")
async def health_history():
    return {
        "total": len(gemini_client.check_history),
        "records": gemini_client.check_history,
    }
