from pydantic import BaseModel, Field
from typing import Optional
from typing import List

class SetupBase(BaseModel):
    production_line_id: int = Field(..., description="ID da linha de produção")
    from_composition_line_id: int = Field(..., description="ID da composition line origem")
    to_composition_line_id: int = Field(..., description="ID da composition line destino")
    setup_time: int = Field(..., ge=0, description="Tempo de setup em segundos")

class ProductResume(BaseModel):
    id: int
    name: str

class MoldResume(BaseModel):
    id: int
    name: str
    
    class Config:
        from_attributes = True

class MachineResume(BaseModel):
    id: int
    name: str
    
    class Config:
        from_attributes = True

class SetupBatchUpdateItem(BaseModel):
    id: int
    setup_time: int

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

class SetupTrocaResponse(BaseModel):
    id: int
    production_line_id: int
    from_composition_line_id: int
    to_composition_line_id: int
    name: str
    setup_time: int
    from_product: ProductResume
    from_mold: MoldResume
    to_product: ProductResume
    to_mold: MoldResume

    class Config:
        from_attributes = True

class ProductionLineResume(BaseModel):
    id: int
    name: str
    
    class Config:
        from_attributes = True

class CompositionLineResume(BaseModel):
    id: int
    mold_name: str
    product_name: str
    name: str  # Concatenação de mold.name + product.name
    
    class Config:
        from_attributes = True

class SetupResumeResponse(BaseModel):
    id: int
    name: str
    setup_time: int
    from_composition_line: CompositionLineResume
    to_composition_line: CompositionLineResume

    class Config:
        from_attributes = True

class SetupBatchUpdateRequest(BaseModel):
    updates: List[SetupBatchUpdateItem]