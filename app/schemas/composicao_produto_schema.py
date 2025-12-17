from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field
from app.schemas.materia_prima_schema import MateriaPrimaResponse
from app.schemas.product_schema import ProductResponse

class ComposicaoProdutoBase(BaseModel):
    produto_id: int
    materia_prima_id: int
    quantidade: Decimal = Field(..., ge=0, description="Quantidade em Kg ou 0.00")

class ComposicaoProdutoCreate(ComposicaoProdutoBase):
    pass

class ComposicaoProdutoUpdate(ComposicaoProdutoBase):
    pass

class ComposicaoProdutoResponse(ComposicaoProdutoBase):
    id: int
    produto: Optional[ProductResponse] = None
    materia_prima: Optional[MateriaPrimaResponse] = None

    class Config:
        from_attributes = True

