from decimal import Decimal
from pydantic import BaseModel, Field

class MaquinaBase(BaseModel):
    cod_maquina: str = Field(..., description="Código da máquina")
    disponibilidade: Decimal = Field(..., ge=0.01, le=100, description="Disponibilidade em porcentagem (0.01 a 100)")

class MaquinaCreate(MaquinaBase):
    pass

class MaquinaUpdate(MaquinaBase):
    pass

class MaquinaResponse(MaquinaBase):
    id: int

    class Config:
        from_attributes = True

