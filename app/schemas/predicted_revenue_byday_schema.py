from pydantic import BaseModel
from datetime import date

class PredictedRevenueByDayBase(BaseModel):
    billing_date: date
    revenue_total: float

class PredictedRevenueByDayCreate(PredictedRevenueByDayBase):
    pass

class PredictedRevenueByDayResponse(PredictedRevenueByDayBase):
    id: int

    class Config:
        orm_mode = True
