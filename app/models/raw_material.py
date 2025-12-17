from sqlalchemy import Column, Integer, String, DECIMAL
from app.database import Base

class RawMaterial(Base):
    __tablename__ = "materia_prima"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, nullable=False)
    lead_time_medio_entrega = Column(Integer, nullable=False)
    custo_medio = Column(DECIMAL, nullable=False)



