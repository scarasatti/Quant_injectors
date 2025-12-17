from pydantic import BaseModel, Field
from typing import List, Optional

class CompositionLineInfo(BaseModel):
    """Composition line information in response"""
    id: int
    mold_id: int
    product_id: int
    mold_name: str
    product_name: str
    
    class Config:
        from_attributes = True

class ProductionLineBase(BaseModel):
    name: str = Field(..., description="Production line name")

class ProductionLineCreate(ProductionLineBase):
    pass

class ProductionLineUpdate(BaseModel):
    name: Optional[str] = Field(None, description="Production line name")

class ProductionLineResponse(ProductionLineBase):
    id: int
    composition_lines: List[CompositionLineInfo] = Field(default=[], description="Composition lines in this production line")
    
    class Config:
        from_attributes = True
