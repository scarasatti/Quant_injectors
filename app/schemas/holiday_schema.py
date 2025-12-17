from datetime import date as date_type
from typing import Optional

from pydantic import BaseModel, Field

from app.models.holiday import HolidayLevel


class HolidayBase(BaseModel):
    name: str
    date: date_type = Field(..., description="Data do feriado")
    level: HolidayLevel
    state: Optional[str] = Field(
        default=None, description="Sigla do estado (opcional para feriados nacionais)"
    )
    city: Optional[str] = Field(
        default=None, description="Nome do município (opcional)"
    )


class HolidayCreate(HolidayBase):
    pass


class HolidayUpdate(BaseModel):
    name: Optional[str] = None
    date: Optional[date_type] = None
    level: Optional[HolidayLevel] = None
    state: Optional[str] = None
    city: Optional[str] = None


class HolidayResponse(HolidayBase):
    id: int

    class Config:
        from_attributes = True



