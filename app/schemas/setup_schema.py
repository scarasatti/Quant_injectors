from pydantic import BaseModel
from typing import Optional

class SetupBase(BaseModel):
    produto_de: int
    produto_para: int
    tempo_setup: int
    menor_produto: Optional[float] = None
    maior_produto: Optional[float] = None

class SetupTrocaCreate(SetupBase):
    pass

class SetupTrocaUpdate(SetupBase):
    pass

class SetupTrocaResponse(SetupBase):
    id: int

    class Config:
        from_attributes = True
