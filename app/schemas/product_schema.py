from decimal import Decimal
from typing import List
from pydantic import BaseModel, Field

class ProductBase(BaseModel):
    name: str

class ProductCreate(ProductBase):
    pass

class ProductUpdate(ProductBase):
    pass

class MoldInfo(BaseModel):
    """Mold information in response"""
    id: int
    total_cavities: int
    open_cavities: int
    scrap: Decimal
    closed_cavity_risk: Decimal
    
    class Config:
        from_attributes = True

class RawMaterialInfo(BaseModel):
    """Raw material information in product composition"""
    id: int
    nome: str
    quantidade: Decimal
    
    class Config:
        from_attributes = True

class ProductResponse(ProductBase):
    id: int
    molds: List[MoldInfo] = Field(default=[], description="Molds that can manufacture this product")
    raw_materials: List[RawMaterialInfo] = Field(default=[], description="Raw materials (compositions) used in this product")
    
    @classmethod
    def from_orm_with_relations(cls, product_obj):
        """Helper method to create response with molds and compositions loaded"""
        molds = [
            MoldInfo(
                id=mp.mold.id,
                total_cavities=mp.mold.total_cavities,
                open_cavities=mp.mold.open_cavities,
                scrap=mp.mold.scrap,
                closed_cavity_risk=mp.mold.closed_cavity_risk
            ) for mp in product_obj.molds
        ]
        
        raw_materials = [
            RawMaterialInfo(
                id=comp.materia_prima.id,
                nome=comp.materia_prima.nome,
                quantidade=comp.quantidade
            ) for comp in product_obj.compositions
        ]
        
        return cls(
            id=product_obj.id,
            name=product_obj.name,
            molds=molds,
            raw_materials=raw_materials
        )

    class Config:
        from_attributes = True
