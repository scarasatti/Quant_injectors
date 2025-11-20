from sqlalchemy import Column, Integer, String, DECIMAL
from sqlalchemy.orm import relationship
from app.database import Base

class Maquina(Base):
    __tablename__ = "maquina"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    cod_maquina = Column(String, nullable=False)
    disponibilidade = Column(DECIMAL(precision=5, scale=2), nullable=False)
    
    # Relação 1:N com linhas de produção (1 máquina tem N linhas)
    production_lines = relationship("ProductionLine", back_populates="maquina")

