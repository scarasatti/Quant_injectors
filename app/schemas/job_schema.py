from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class JobBase(BaseModel):
    name: str
    promised_date: Optional[datetime] = None
    demand: Optional[int] = None
    product_value: Optional[float] = None
    processed: Optional[bool] = None
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
