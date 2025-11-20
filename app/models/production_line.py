from sqlalchemy import Column, Integer, String, DECIMAL, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

class ProductionLine(Base):
    __tablename__ = "production_line"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    mold_code = Column(String, nullable=False)
    product = Column(String, nullable=False)
    total_cavities = Column(Integer, nullable=False)
    open_cavities = Column(Integer, nullable=False)
    cycle_time = Column(Integer, nullable=False)
    post_injection_cycle_time = Column(Integer, nullable=False)
    scrap = Column(DECIMAL(precision=5, scale=2), nullable=False)  # 0 to 100%
    absorb_closed_cavity = Column(DECIMAL(precision=5, scale=2), nullable=False)  # 0 to 100%
    line_number = Column(Integer, nullable=False)  # int >= 1
    
    # Relação 1:N com máquina (1 máquina tem N linhas de produção)
    fk_id_maquina = Column(Integer, ForeignKey("maquina.id"), nullable=False)
    
    maquina = relationship("Maquina", back_populates="production_lines")

