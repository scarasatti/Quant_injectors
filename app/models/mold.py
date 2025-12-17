from sqlalchemy import Column, Integer, String, DECIMAL
from sqlalchemy.orm import relationship
from app.database import Base

class Mold(Base):
    __tablename__ = "mold"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String, nullable=False)
    total_cavities = Column(Integer, nullable=False)
    open_cavities = Column(Integer, nullable=False)
    scrap = Column(DECIMAL(precision=5, scale=2), nullable=False)  # 0 to 100%
    closed_cavity_risk = Column(DECIMAL(precision=5, scale=2), nullable=False)  # 0 to 100%
    
    # N:N relationship with products through intermediate table
    products = relationship("MoldProduct", back_populates="mold", cascade="all, delete-orphan")
    
    # 1:N relationship with production times (a mold can have multiple production times with different machines/products)
    production_times = relationship("ProductionTime", back_populates="mold", cascade="all, delete-orphan")
    
    # 1:N relationship with composition lines
    composition_lines = relationship("CompositionLine", back_populates="mold", cascade="all, delete-orphan")

