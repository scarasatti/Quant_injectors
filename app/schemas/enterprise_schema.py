from pydantic import BaseModel, EmailStr

class EnterpriseCreate(BaseModel):
    name: str
    representative_email: EmailStr
    access_count: int
    model_type: str

class EnterpriseOut(BaseModel):
    id: int
    name: str
    representative_email: EmailStr
    access_count: int

    class Config:
        from_attributes = True
