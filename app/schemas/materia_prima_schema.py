from decimal import Decimal
from pydantic import BaseModel, Field

class MateriaPrimaBase(BaseModel):
    nome: str
    lead_time_medio_entrega: int = Field(..., ge=0, description="Lead time médio de entrega em dias")
    custo_medio: Decimal = Field(..., ge=0, description="Custo médio da matéria prima")

class MateriaPrimaCreate(MateriaPrimaBase):
    pass

class MateriaPrimaUpdate(MateriaPrimaBase):
    pass

class MateriaPrimaResponse(MateriaPrimaBase):
    id: int

    class Config:
        from_attributes = True



