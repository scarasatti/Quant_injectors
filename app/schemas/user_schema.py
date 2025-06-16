from pydantic import BaseModel, EmailStr, field_validator
import re

class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str
    enterprise_id: int
    token: str  # token de cadastro fornecido pela empresa

    @classmethod
    @field_validator("password")
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError("A senha deve ter no mínimo 8 caracteres.")
        if not re.search(r"[a-z]", v):
            raise ValueError("A senha deve conter ao menos uma letra minúscula.")
        if not re.search(r"[A-Z]", v):
            raise ValueError("A senha deve conter ao menos uma letra maiúscula.")
        if not re.search(r"[0-9]", v):
            raise ValueError("A senha deve conter ao menos um número.")
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", v):
            raise ValueError("A senha deve conter ao menos um caractere especial.")
        return v

class UserOut(BaseModel):
    id: int
    name: str
    email: EmailStr

    class Config:
        from_attributes = True
