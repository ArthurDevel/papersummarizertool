import logging
from typing import List
from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy.orm import Session
from users import client as users_client
from paperprocessor.client import get_processing_metrics_for_user, get_processing_metrics_for_admin
from api.types.user_api_models import (
    SyncUserPayload,
    UserListItem,
    UserRequestItem,
    ExistsResponse,
    CreatedResponse,
    DeletedResponse,
)
from shared.db import get_session

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/users/sync", status_code=201)
async def sync_user(payload: SyncUserPayload, db: Session = Depends(get_session)):
    """
    This endpoint is called by a BetterAuth hook after a new user signs up.
    It's responsible for creating a corresponding user record in our own database.
    """
    logger.info(f"Received request to sync user. Passing to users client.")
    
    result = await users_client.sync_new_user(
        db=db,
        auth_provider_id=payload.id,
        email=payload.email,
    )
    
    return result


def _require_auth_provider_id(x_auth_provider_id: str | None) -> str:
    if not x_auth_provider_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing X-Auth-Provider-Id header")
    return x_auth_provider_id


@router.get("/users/me/papers/{paper_uuid}/processing_metrics")
async def get_my_processing_metrics(
    paper_uuid: str,
    db: Session = Depends(get_session),
    x_auth_provider_id: str | None = Header(default=None, convert_underscores=False, alias="X-Auth-Provider-Id"),
):
    user_id = _require_auth_provider_id(x_auth_provider_id)
    try:
        # DB dependency kept to be consistent with other endpoints; client method uses its own session
        _ = db  # unused but kept for signature consistency
        result = get_processing_metrics_for_user(paper_uuid, user_id)
        return result
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paper not found")
    except RuntimeError as e:
        # Not completed yet
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except PermissionError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


@router.post("/users/me/list/{paper_uuid}", response_model=CreatedResponse)
async def add_to_list(
    paper_uuid: str,
    response: Response,
    db: Session = Depends(get_session),
    x_auth_provider_id: str | None = Header(default=None, convert_underscores=False, alias="X-Auth-Provider-Id"),
):
    user_id = _require_auth_provider_id(x_auth_provider_id)
    try:
        result = await users_client.add_list_entry(db=db, auth_provider_id=user_id, paper_uuid=paper_uuid)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    if result.get("created"):
        response.status_code = status.HTTP_201_CREATED
    return CreatedResponse(created=bool(result.get("created")))


@router.delete("/users/me/list/{paper_uuid}", response_model=DeletedResponse)
async def remove_from_list(
    paper_uuid: str,
    db: Session = Depends(get_session),
    x_auth_provider_id: str | None = Header(default=None, convert_underscores=False, alias="X-Auth-Provider-Id"),
):
    user_id = _require_auth_provider_id(x_auth_provider_id)
    try:
        result = await users_client.remove_list_entry(db=db, auth_provider_id=user_id, paper_uuid=paper_uuid)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return DeletedResponse(deleted=bool(result.get("deleted")))


@router.get("/users/me/list", response_model=List[UserListItem])
async def get_my_list(
    db: Session = Depends(get_session),
    x_auth_provider_id: str | None = Header(default=None, convert_underscores=False, alias="X-Auth-Provider-Id"),
):
    user_id = _require_auth_provider_id(x_auth_provider_id)
    try:
        items = await users_client.list_user_entries(db=db, auth_provider_id=user_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return [UserListItem(**it) for it in items]


@router.get("/users/me/list/{paper_uuid}", response_model=ExistsResponse)
async def check_in_list(
    paper_uuid: str,
    db: Session = Depends(get_session),
    x_auth_provider_id: str | None = Header(default=None, convert_underscores=False, alias="X-Auth-Provider-Id"),
):
    user_id = _require_auth_provider_id(x_auth_provider_id)
    try:
        result = await users_client.is_entry_present(db=db, auth_provider_id=user_id, paper_uuid=paper_uuid)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return ExistsResponse(**result)


# --- User Requests ---

@router.post("/users/me/requests/{arxiv_id}", response_model=CreatedResponse)
async def add_request(
    arxiv_id: str,
    response: Response,
    db: Session = Depends(get_session),
    x_auth_provider_id: str | None = Header(default=None, convert_underscores=False, alias="X-Auth-Provider-Id"),
):
    user_id = _require_auth_provider_id(x_auth_provider_id)
    try:
        result = await users_client.add_request_entry(db=db, auth_provider_id=user_id, arxiv_id=arxiv_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    if result.get("created"):
        response.status_code = status.HTTP_201_CREATED
    return CreatedResponse(created=bool(result.get("created")))


@router.delete("/users/me/requests/{arxiv_id}", response_model=DeletedResponse)
async def remove_request(
    arxiv_id: str,
    db: Session = Depends(get_session),
    x_auth_provider_id: str | None = Header(default=None, convert_underscores=False, alias="X-Auth-Provider-Id"),
):
    user_id = _require_auth_provider_id(x_auth_provider_id)
    try:
        result = await users_client.remove_request_entry(db=db, auth_provider_id=user_id, arxiv_id=arxiv_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return DeletedResponse(deleted=bool(result.get("deleted")))


@router.get("/users/me/requests", response_model=List[UserRequestItem])
async def list_my_requests(
    db: Session = Depends(get_session),
    x_auth_provider_id: str | None = Header(default=None, convert_underscores=False, alias="X-Auth-Provider-Id"),
):
    user_id = _require_auth_provider_id(x_auth_provider_id)
    try:
        items = await users_client.list_user_requests(db=db, auth_provider_id=user_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return [UserRequestItem(**it) for it in items]


@router.get("/users/me/requests/{arxiv_id}", response_model=ExistsResponse)
async def does_request_exist(
    arxiv_id: str,
    db: Session = Depends(get_session),
    x_auth_provider_id: str | None = Header(default=None, convert_underscores=False, alias="X-Auth-Provider-Id"),
):
    user_id = _require_auth_provider_id(x_auth_provider_id)
    try:
        result = await users_client.does_request_exist(db=db, auth_provider_id=user_id, arxiv_id=arxiv_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return ExistsResponse(**result)
