from pydantic import BaseModel
from datetime import datetime

class UserSessionResponse(BaseModel):
    id: int
    user_id: int
    token: str
    created_at: datetime
    is_active: bool

    class Config:
        from_attributes = True
