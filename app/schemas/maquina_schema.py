from decimal import Decimal
from pydantic import BaseModel, Field
from typing import Optional

class MachineBase(BaseModel):
    name: str = Field(..., description="Machine name")
    availability: Decimal = Field(..., ge=0.01, le=100, description="Availability percentage (0.01 to 100)")

class MachineCreate(MachineBase):
    pass

class MachineUpdate(MachineBase):
    pass

class MachineResponse(MachineBase):
    id: int

    class Config:
        from_attributes = True


