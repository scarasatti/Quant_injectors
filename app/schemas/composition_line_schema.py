from pydantic import BaseModel, Field
from typing import List, Optional

class CompositionLineBase(BaseModel):
    production_line_id: int = Field(..., description="Production line ID")
    mold_id: int = Field(..., description="Mold ID")
    product_id: int = Field(..., description="Product ID (must belong to the mold)")
    post_injection_cycle_time: int = Field(..., ge=0, description="Post-injection cycle time in seconds")

class CompositionLineCreate(CompositionLineBase):
    machines: List[int] = Field(..., min_length=1, description="List of machine IDs for this composition line (at least one required)")

class CompositionLineUpdate(BaseModel):
    production_line_id: Optional[int] = Field(None, description="Production line ID")
    mold_id: Optional[int] = Field(None, description="Mold ID")
    product_id: Optional[int] = Field(None, description="Product ID (must belong to the mold)")
    post_injection_cycle_time: Optional[int] = Field(None, ge=0, description="Post-injection cycle time in seconds")
    machines: Optional[List[int]] = Field(None, min_length=1, description="List of machine IDs for this composition line")

class MachineInfo(BaseModel):
    """Machine information in response"""
    id: int
    name: str
    availability: float
    cycle_time: int
    
    class Config:
        from_attributes = True

class ProductionLineInfo(BaseModel):
    """Production line information in response"""
    id: int
    name: str
    
    class Config:
        from_attributes = True

class MoldInfo(BaseModel):
    """Mold information in response"""
    id: int
    name: str
    
    class Config:
        from_attributes = True

class ProductInfo(BaseModel):
    """Product information in response"""
    id: int
    name: str
    
    class Config:
        from_attributes = True

class CompositionLineResponse(CompositionLineBase):
    id: int
    production_line: ProductionLineInfo
    mold: MoldInfo
    product: ProductInfo
    machines: List[MachineInfo] = Field(default=[], description="Machines in this composition line")
    
    @classmethod
    def from_orm_with_relations(cls, composition_line_obj, db=None):
        """Helper method to create response with related entities loaded.
        Cycle time is retrieved from ProductionTime table."""
        from app.models.production_time import ProductionTime
        
        machines = []
        for clm in composition_line_obj.machines:
            # Get cycle time from ProductionTime based on machine, product, and mold
            production_time = db.query(ProductionTime).filter(
                ProductionTime.machine_id == clm.machine_id,
                ProductionTime.product_id == composition_line_obj.product_id,
                ProductionTime.mold_id == composition_line_obj.mold_id
            ).first()
            
            cycle_time = production_time.tempo_ciclo if production_time else 0
            
            machines.append(
                MachineInfo(
                    id=clm.machine.id,
                    name=clm.machine.name,
                    availability=float(clm.machine.availability),
                    cycle_time=cycle_time
                )
            )
        
        return cls(
            id=composition_line_obj.id,
            production_line_id=composition_line_obj.production_line_id,
            mold_id=composition_line_obj.mold_id,
            product_id=composition_line_obj.product_id,
            post_injection_cycle_time=composition_line_obj.post_injection_cycle_time,
            production_line=ProductionLineInfo(
                id=composition_line_obj.production_line.id,
                name=composition_line_obj.production_line.name
            ),
            mold=MoldInfo(
                id=composition_line_obj.mold.id,
                name=composition_line_obj.mold.name
            ),
            product=ProductInfo(
                id=composition_line_obj.product.id,
                name=composition_line_obj.product.name
            ),
            machines=machines
        )
    
    class Config:
        from_attributes = True


