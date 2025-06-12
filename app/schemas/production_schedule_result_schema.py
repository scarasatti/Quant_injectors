from pydantic import BaseModel
from datetime import date, time

class ProductionScheduleResultBase(BaseModel):
    job_id: int
    order_index: int
    client_name: str
    product_name: str
    quantity: int
    scheduled_date: date
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
