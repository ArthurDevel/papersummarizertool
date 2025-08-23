import logging
from pydantic import EmailStr
from typing import List, Dict, Any
from sqlalchemy.orm import Session

from api.models import PaperRow, PaperSlugRow
from users.models import UserRow, UserListRow

logger = logging.getLogger(__name__)

async def sync_new_user(db: Session, auth_provider_id: str, email: EmailStr):
    """
    Ensure a user record exists for the given auth provider id.
    Idempotent: create only if not present.
    """
    logger.info(
        f"Syncing new user in users client. Auth Provider ID: {auth_provider_id}, Email: {email}"
    )
    user = db.query(UserRow).filter(UserRow.id == auth_provider_id).first()
    if user:
        # Optionally update email if changed
        try:
            if user.email != str(email):
                user.email = str(email)
                db.add(user)
                db.commit()
        except Exception:
            logger.exception("Failed to update email for user %s", auth_provider_id)
        return {"status": "ok", "created": False}

    user = UserRow(id=auth_provider_id, email=str(email))
    db.add(user)
    db.commit()
    return {"status": "ok", "created": True}


async def add_list_entry(db: Session, auth_provider_id: str, paper_uuid: str) -> Dict[str, bool]:
    """
    Add a paper to the user's list. Idempotent: returns created=False if already present.
    """
    user = db.query(UserRow).filter(UserRow.id == auth_provider_id).first()
    if not user:
        raise ValueError("User not found")
    paper = db.query(PaperRow).filter(PaperRow.paper_uuid == paper_uuid).first()
    if not paper:
        raise ValueError("Paper not found")
    existing = (
        db.query(UserListRow)
        .filter(UserListRow.user_id == user.id, UserListRow.paper_id == paper.id)
        .first()
    )
    if existing:
        return {"created": False}
    entry = UserListRow(user_id=user.id, paper_id=paper.id)
    db.add(entry)
    db.commit()
    return {"created": True}


async def remove_list_entry(db: Session, auth_provider_id: str, paper_uuid: str) -> Dict[str, bool]:
    user = db.query(UserRow).filter(UserRow.id == auth_provider_id).first()
    if not user:
        raise ValueError("User not found")
    paper = db.query(PaperRow).filter(PaperRow.paper_uuid == paper_uuid).first()
    if not paper:
        raise ValueError("Paper not found")
    q = (
        db.query(UserListRow)
        .filter(UserListRow.user_id == user.id, UserListRow.paper_id == paper.id)
    )
    deleted = q.delete()
    db.commit()
    return {"deleted": bool(deleted)}


async def is_entry_present(db: Session, auth_provider_id: str, paper_uuid: str) -> Dict[str, bool]:
    user = db.query(UserRow).filter(UserRow.id == auth_provider_id).first()
    if not user:
        raise ValueError("User not found")
    paper = db.query(PaperRow).filter(PaperRow.paper_uuid == paper_uuid).first()
    if not paper:
        return {"exists": False}
    exists = (
        db.query(UserListRow)
        .filter(UserListRow.user_id == user.id, UserListRow.paper_id == paper.id)
        .first()
        is not None
    )
    return {"exists": exists}


async def list_user_entries(db: Session, auth_provider_id: str) -> List[Dict[str, Any]]:
    """
    Return enriched paper items in the user's list.
    Includes latest non-tombstoned slug when available.
    """
    user = db.query(UserRow).filter(UserRow.id == auth_provider_id).first()
    if not user:
        raise ValueError("User not found")

    # Join user_lists -> papers
    entries = (
        db.query(PaperRow)
        .join(UserListRow, UserListRow.paper_id == PaperRow.id)
        .filter(UserListRow.user_id == user.id)
        .all()
    )

    # Fetch slugs for these papers
    paper_uuid_list = [p.paper_uuid for p in entries]
    slugs_by_uuid: Dict[str, str] = {}
    if paper_uuid_list:
        slug_rows = (
            db.query(PaperSlugRow)
            .filter(PaperSlugRow.paper_uuid.in_(paper_uuid_list))
            .filter(PaperSlugRow.tombstone == False)  # noqa: E712
            .all()
        )
        for r in slug_rows:
            current = slugs_by_uuid.get(r.paper_uuid)
            if current is None:
                slugs_by_uuid[r.paper_uuid] = r.slug

    items: List[Dict[str, Any]] = []
    for p in entries:
        items.append(
            {
                "paper_uuid": p.paper_uuid,
                "title": getattr(p, "title", None),
                "authors": getattr(p, "authors", None),
                "thumbnail_data_url": getattr(p, "thumbnail_data_url", None),
                "slug": slugs_by_uuid.get(p.paper_uuid),
            }
        )
    return items
