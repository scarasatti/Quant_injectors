from pydantic import BaseModel


class EnterpriseCreate(BaseModel):
    name: str


class EnterpriseOut(BaseModel):
    id: int
    name: str

    class Config:
        orm_mode = True
