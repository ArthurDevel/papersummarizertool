import logging
from pydantic import EmailStr

logger = logging.getLogger(__name__)

async def sync_new_user(auth_provider_id: str, email: EmailStr):
    """
    Handles the business logic for synchronizing a new user from the auth provider
    to our own database.
    """
    logger.info(f"Syncing new user in users client. Auth Provider ID: {auth_provider_id}, Email: {email}")

    # TODO: Implement the database logic here.
    # This is where the database call to create a new user record will go.

    return {"status": "ok", "message": "User sync initiated in client."}
