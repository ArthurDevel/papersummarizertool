import logging
from fastapi import APIRouter
from users import client as users_client
from api.types.user_api_models import SyncUserPayload

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/users/sync", status_code=201)
async def sync_user(payload: SyncUserPayload):
    """
    This endpoint is called by a BetterAuth hook after a new user signs up.
    It's responsible for creating a corresponding user record in our own database.
    """
    logger.info(f"Received request to sync user. Passing to users client.")
    
    result = await users_client.sync_new_user(
        auth_provider_id=payload.id,
        email=payload.email
    )
    
    return result
