from decimal import Decimal
from pydantic import BaseModel, Field

class ProductBase(BaseModel):
    name: str
    cycle: int
    bottleneck: int
    scrap: Decimal = Field(..., ge=0, le=100, description="Porcentagem de refugo deve estar entre 0 e 100")

class ProductCreate(ProductBase):
    pass

class ProductUpdate(ProductBase):
    pass

class ProductResponse(ProductBase):
    id: int

    class Config:
        from_attributes = True
