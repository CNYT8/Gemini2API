import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/model-mapping", tags=["Model Mapping"])


class SetMappingRequest(BaseModel):
    alias: str
    target: str


@router.get("")
async def get_mappings(request: Request):
    mm = request.app.state.model_mapping
    return {"mappings": mm.get_all()}


@router.post("")
async def set_mapping(req: SetMappingRequest, request: Request):
    if not req.alias or not req.target:
        raise HTTPException(status_code=400, detail="alias and target are required")
    if req.alias == req.target:
        raise HTTPException(status_code=400, detail="alias cannot equal target")
    mm = request.app.state.model_mapping
    mm.set(req.alias, req.target)
    return {"success": True, "mappings": mm.get_all()}


@router.delete("/{alias}")
async def delete_mapping(alias: str, request: Request):
    mm = request.app.state.model_mapping
    if not mm.delete(alias):
        raise HTTPException(status_code=404, detail=f"Mapping '{alias}' not found")
    return {"success": True, "mappings": mm.get_all()}
