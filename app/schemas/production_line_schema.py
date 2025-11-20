from decimal import Decimal
from pydantic import BaseModel, Field

class ProductionLineBase(BaseModel):
    mold_code: str = Field(..., description="Código do molde")
    product: str = Field(..., description="Produto")
    total_cavities: int = Field(..., ge=1, description="Total de cavidades")
    open_cavities: int = Field(..., ge=0, description="Cavidades abertas")
    cycle_time: int = Field(..., ge=0, description="Tempo de ciclo")
    post_injection_cycle_time: int = Field(..., ge=0, description="Tempo de ciclo pós-injeção")
    scrap: Decimal = Field(..., ge=0, le=100, description="Refugo em porcentagem (0 a 100)")
    absorb_closed_cavity: Decimal = Field(..., ge=0, le=100, description="Absorver cavidade fechada em porcentagem (0 a 100)")
    line_number: int = Field(..., ge=1, description="Número da linha (>= 1)")
    fk_id_maquina: int = Field(..., description="ID da máquina")

class ProductionLineCreate(ProductionLineBase):
    pass

class ProductionLineUpdate(ProductionLineBase):
    pass

class ProductionLineResponse(ProductionLineBase):
    id: int

    class Config:
        from_attributes = True

