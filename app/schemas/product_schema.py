from pydantic import BaseModel

class ProductBase(BaseModel):
    name: str
    ciclo: int


class ProductCreate(ProductBase):
    pass

class ProductUpdate(ProductBase):
    pass

class ProductResponse(ProductBase):
    id: int

    class Config:
        from_attributes = True
