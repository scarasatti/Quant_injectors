from pydantic import BaseModel
from typing import Optional
from typing import List

class SetupBase(BaseModel):
    from_product: int
    to_product: int
    setup_time: int

class ProductResume(BaseModel):
    id: int
    name: str


class SetupBatchItem(BaseModel):
    product_id: int
    setup_time: int

class SetupBatchCreate(BaseModel):
    product_ref: int
    setups: List[SetupBatchItem]

class SetupTrocaCreate(SetupBase):
    pass

class SetupTrocaUpdate(SetupBase):
    pass

class SetupTrocaResponse(SetupBase):
    id: int

    class Config:
        from_attributes = True

class SetupResumeResponse(BaseModel):
    id: int
    setup_time: int
    pair_product: ProductResume

    class Config:
        from_attributes = True
