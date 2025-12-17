from enum import Enum as PyEnum
from typing import Optional
from datetime import time

from pydantic import BaseModel, Field


class DiaSemana(str, PyEnum):
    SEGUNDA = "Segunda-feira"
    TERCA = "Terça-feira"
    QUARTA = "Quarta-feira"
    QUINTA = "Quinta-feira"
    SEXTA = "Sexta-feira"
    SABADO = "Sábado"
    DOMINGO = "Domingo"


class FrequenciaTurno(str, PyEnum):
    DIARIO = "Diário"
    QUINZENAL = "Quinzenal"
    NAO_TRABALHA = "Não Trabalha"


class RegularShiftBase(BaseModel):
    dia_semana: DiaSemana
    manha: bool = Field(default=False)
    tarde: bool = Field(default=False)
    noite: bool = Field(default=False)
    frequencia: FrequenciaTurno

    # Horários de início/fim (opcionais)
    manha_inicio: Optional[time] = None
    manha_fim: Optional[time] = None
    tarde_inicio: Optional[time] = None
    tarde_fim: Optional[time] = None
    noite_inicio: Optional[time] = None
    noite_fim: Optional[time] = None


class RegularShiftCreate(RegularShiftBase):
    pass


class RegularShiftUpdate(BaseModel):
    manha: Optional[bool] = None
    tarde: Optional[bool] = None
    noite: Optional[bool] = None
    frequencia: Optional[FrequenciaTurno] = None

    manha_inicio: Optional[time] = None
    manha_fim: Optional[time] = None
    tarde_inicio: Optional[time] = None
    tarde_fim: Optional[time] = None
    noite_inicio: Optional[time] = None
    noite_fim: Optional[time] = None


class RegularShiftResponse(RegularShiftBase):
    id: int

    class Config:
        from_attributes = True
