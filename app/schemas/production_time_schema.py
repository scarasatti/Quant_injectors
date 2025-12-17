from pydantic import BaseModel, Field, field_validator
from typing import Optional

class ProductionTimeBase(BaseModel):
    tempo_ciclo: int = Field(..., gt=0, description="Cycle time in seconds")
    machine_id: int = Field(..., description="Machine ID (1:1 relationship)")
    product_id: int = Field(..., description="Product ID (1:1 relationship)")
    mold_id: int = Field(..., description="Mold ID (1:1 relationship)")

class ProductionTimeCreate(ProductionTimeBase):
    pass

class ProductionTimeUpdate(BaseModel):
    tempo_ciclo: Optional[int] = Field(None, gt=0, description="Cycle time in seconds")
    machine_id: Optional[int] = Field(None, description="Machine ID (1:1 relationship)")
    product_id: Optional[int] = Field(None, description="Product ID (1:1 relationship)")
    mold_id: Optional[int] = Field(None, description="Mold ID (1:1 relationship)")

class MachineInfo(BaseModel):
    """Machine information in response"""
    id: int
    name: str
    availability: float
    
    class Config:
        from_attributes = True

class ProductInfo(BaseModel):
    """Product information in response"""
    id: int
    name: str
    
    class Config:
        from_attributes = True

class MoldInfo(BaseModel):
    """Mold information in response"""
    id: int
    name: str
    total_cavities: int
    open_cavities: int
    
    class Config:
        from_attributes = True

class ProductionTimeResponse(ProductionTimeBase):
    id: int
    machine: MachineInfo
    product: ProductInfo
    mold: MoldInfo
    
    @classmethod
    def from_orm_with_relations(cls, production_time_obj):
        """Helper method to create response with related entities loaded"""
        return cls(
            id=production_time_obj.id,
            tempo_ciclo=production_time_obj.tempo_ciclo,
            machine_id=production_time_obj.machine_id,
            product_id=production_time_obj.product_id,
            mold_id=production_time_obj.mold_id,
            machine=MachineInfo(
                id=production_time_obj.machine.id,
                name=production_time_obj.machine.name,
                availability=float(production_time_obj.machine.availability)
            ),
            product=ProductInfo(
                id=production_time_obj.product.id,
                name=production_time_obj.product.name
            ),
            mold=MoldInfo(
                id=production_time_obj.mold.id,
                name=production_time_obj.mold.name,
                total_cavities=production_time_obj.mold.total_cavities,
                open_cavities=production_time_obj.mold.open_cavities
            )
        )

    class Config:
        from_attributes = True

