from pydantic import BaseModel, EmailStr

class SyncUserPayload(BaseModel):
    id: str
    email: EmailStr
