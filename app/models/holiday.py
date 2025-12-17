from enum import Enum as PyEnum
from sqlalchemy import Column, Integer, String, Date
from sqlalchemy import Enum as SqlEnum
from app.database import Base

class HolidayLevel(str, PyEnum):
    NACIONAL = "Nacional"
    ESTADUAL = "Estadual"
    REGIONAL = "Regional"
    MUNICIPAL = "Municipal"


class Holiday(Base):
    __tablename__ = "holidays"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    date = Column(Date, unique=True, nullable=False)
    level = Column(SqlEnum(HolidayLevel), nullable=False)
    state = Column(String, nullable=True)
    city = Column(String, nullable=True)





















