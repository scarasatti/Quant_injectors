from sqlalchemy import Column, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database import Base

class ProductionTime(Base):
    """
    Production time table with 1:1 relationships to Machine, Product, and Mold.
    Represents the cycle time for a specific combination of machine, product, and mold.
    
    Important: The product must belong to the specified mold (validated in routes).
    """
    __tablename__ = "production_time"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tempo_ciclo = Column(Integer, nullable=False)  # Cycle time in seconds
    
    # Foreign keys - each production time has one machine, one product, and one mold
    machine_id = Column(Integer, ForeignKey("machine.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    mold_id = Column(Integer, ForeignKey("mold.id"), nullable=False)
    
    # Relationships
    machine = relationship("Machine", back_populates="production_times")
    product = relationship("Product", back_populates="production_times")
    mold = relationship("Mold", back_populates="production_times")
    
    # Constraint: ensure unique combination
    __table_args__ = (
        UniqueConstraint('machine_id', 'product_id', 'mold_id', name='uq_production_time'),
    )

