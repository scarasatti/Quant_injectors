from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

class CompositionLine(Base):
    """
    CompositionLine represents a composition within a production line.
    Each composition line has:
    - One ProductionLine (parent)
    - One Mold
    - One Product (must belong to the mold via MoldProduct)
    - Multiple Machines (through CompositionLineMachine)
    - Post-injection cycle time
    """
    __tablename__ = "composition_line"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    production_line_id = Column(Integer, ForeignKey("production_line.id"), nullable=False)
    mold_id = Column(Integer, ForeignKey("mold.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    post_injection_cycle_time = Column(Integer, nullable=False)  # Post-injection cycle time in seconds
    
    # Relationships
    production_line = relationship("ProductionLine", back_populates="composition_lines")
    mold = relationship("Mold", back_populates="composition_lines")
    product = relationship("Product", back_populates="composition_lines")
    
    # N:N relationship with machines through intermediate table
    machines = relationship("CompositionLineMachine", back_populates="composition_line", cascade="all, delete-orphan")
    
    # Setups where this composition line is the source
    setups_from = relationship("Setup", foreign_keys="Setup.from_composition_line_id", back_populates="from_composition_line")
    # Setups where this composition line is the destination
    setups_to = relationship("Setup", foreign_keys="Setup.to_composition_line_id", back_populates="to_composition_line")


