from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class JobBase(BaseModel):
    name: str
    promised_date: Optional[datetime] = None
    sequencing_start_date: Optional[datetime] = None
    total_time_sec: Optional[int] = None
    demand: Optional[int] = None
    total_time_hours: Optional[float] = None
    deadline_days: Optional[int] = None
    deadline_hours: Optional[float] = None
    product_value: Optional[float] = None
    produzido: Optional[int] = None
    fk_id_client: Optional[int] = None
    fk_id_product: Optional[int] = None

class JobCreate(JobBase):
    pass

class JobUpdate(JobBase):
    pass

class JobResponse(JobBase):
    id: int

    class Config:
        from_attributes = True
