from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

class ProductionLine(Base):
    """
    Production Line represents a production line configuration.
    It has:
    - Name
    - N Composition Lines (each with mold, product, and machines)
    """
    __tablename__ = "production_line"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String, nullable=False)  # Production line name
    
    # 1:N relationship with composition lines
    # Each composition line has a mold, product, and machines
    composition_lines = relationship("CompositionLine", back_populates="production_line", cascade="all, delete-orphan")
    
    # 1:N relationship with setups
    # Each production line has a setup matrix for all its composition lines
    setups = relationship("Setup", back_populates="production_line", cascade="all, delete-orphan")

