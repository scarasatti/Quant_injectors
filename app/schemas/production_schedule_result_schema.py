from pydantic import BaseModel
from datetime import date, time
from typing import Optional

class ProductionScheduleResultBase(BaseModel):
    job_id: int
    order_index: int
    client_name: str
    product_name: str
    machine_name: str
    mold_name: str
    quantity: int
    scheduled_date: date
    scheduled_time: Optional[time] = None  # Hora limite prometida (planilha)
    actual_date: date
    completion_time: time
    billing_date: date
    status: str
    expected_revenue: float

class ProductionScheduleResultCreate(ProductionScheduleResultBase):
    pass

class ProductionScheduleResultResponse(ProductionScheduleResultBase):
    id: int

    class Config:
        from_attributes = True
