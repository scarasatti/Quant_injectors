from sqlalchemy import Column, Integer, String, DECIMAL
from sqlalchemy.orm import relationship
from app.database import Base

class Machine(Base):
    __tablename__ = "machine"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String, nullable=False)
    availability = Column(DECIMAL(precision=5, scale=2), nullable=False)
    
    # 1:N relationship with production times (a machine can have multiple production times with different products/molds)
    production_times = relationship("ProductionTime", back_populates="machine", cascade="all, delete-orphan")
    
    # N:N relationship with composition lines through intermediate table
    composition_lines = relationship("CompositionLineMachine", back_populates="machine", cascade="all, delete-orphan")