from pydantic import BaseModel, EmailStr

class AccessTokenCreate(BaseModel):
    email: EmailStr
    enterprise_id: int

class AccessTokenValidate(BaseModel):
    token: str
    name: str
    email: EmailStr
    password: str
