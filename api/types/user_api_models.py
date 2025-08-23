from pydantic import BaseModel, EmailStr


class SyncUserPayload(BaseModel):
    id: str
    email: EmailStr


class UserListItem(BaseModel):
    paper_uuid: str
    title: str | None = None
    authors: str | None = None
    thumbnail_data_url: str | None = None
    slug: str | None = None


class ExistsResponse(BaseModel):
    exists: bool


class CreatedResponse(BaseModel):
    created: bool


class DeletedResponse(BaseModel):
    deleted: bool
