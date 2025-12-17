from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, Field

class MoldBase(BaseModel):
    name: str = Field(..., description="Mold name")
    total_cavities: int = Field(..., gt=0, description="Total number of cavities")
    open_cavities: int = Field(..., ge=0, description="Number of open cavities")
    scrap: Decimal = Field(..., ge=0, le=100, description="Scrap percentage (0 to 100)")
    closed_cavity_risk: Decimal = Field(..., ge=0, le=100, description="Closed cavity risk percentage (0 to 100)")

class MoldCreate(MoldBase):
    products: Optional[List[int]] = Field(default=[], description="List of product IDs that can be manufactured by this mold")

class MoldUpdate(MoldBase):
    products: Optional[List[int]] = Field(default=None, description="List of product IDs that can be manufactured by this mold")

class ProductInfo(BaseModel):
    """Product information in response"""
    id: int
    name: str
    
    class Config:
        from_attributes = True

class MoldResponse(MoldBase):
    id: int
    products: List[ProductInfo] = Field(default=[], description="Products that can be manufactured by this mold")
    
    @classmethod
    def from_orm_with_products(cls, mold_obj):
        """Helper method to create response with products loaded"""
        products = [ProductInfo(id=mp.product.id, name=mp.product.name) for mp in mold_obj.products]
        return cls(
            id=mold_obj.id,
            name=mold_obj.name,
            total_cavities=mold_obj.total_cavities,
            open_cavities=mold_obj.open_cavities,
            scrap=mold_obj.scrap,
            closed_cavity_risk=mold_obj.closed_cavity_risk,
            products=products
        )

    class Config:
        from_attributes = True

