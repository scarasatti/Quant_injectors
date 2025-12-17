from enum import Enum as PyEnum

from sqlalchemy import Column, Integer, Boolean, Time
from sqlalchemy import Enum as SqlEnum

from app.database import Base


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


class RegularShift(Base):
    __tablename__ = "regular_shift"

    id = Column(Integer, primary_key=True, index=True)
    dia_semana = Column(SqlEnum(DiaSemana), unique=True, nullable=False)

    # Flags se existe turno neste dia
    manha = Column(Boolean, default=False, nullable=False)
    tarde = Column(Boolean, default=False, nullable=False)
    noite = Column(Boolean, default=False, nullable=False)

    # Frequência do turno (diário, quinzenal, não trabalha)
    frequencia = Column(SqlEnum(FrequenciaTurno), nullable=False)

    # Horários de início/fim de cada turno (opcionais para não quebrar dados antigos)
    manha_inicio = Column(Time, nullable=True)
    manha_fim = Column(Time, nullable=True)

    tarde_inicio = Column(Time, nullable=True)
    tarde_fim = Column(Time, nullable=True)

    noite_inicio = Column(Time, nullable=True)
    noite_fim = Column(Time, nullable=True)
