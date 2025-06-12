from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional
from .production_schedule_result_schema import ProductionScheduleResultResponse
from .predicted_revenue_byday_schema import PredictedRevenueByDayResponse

class ProductionScheduleRunBase(BaseModel):
    sequencing_start: datetime
    setup_count: int
    optimized_setups: int
    on_time_jobs: int
    total_machine_hours: float
    max_deadline_hours: float
    machine_status: str

class ProductionScheduleRunCreate(ProductionScheduleRunBase):
    pass

class ProductionScheduleRunResponse(ProductionScheduleRunBase):
    id: int
    created_at: datetime
    results: Optional[List[ProductionScheduleResultResponse]] = []
    revenue_forecast: Optional[List[PredictedRevenueByDayResponse]] = []

    class Config:
        from_attributes = True
