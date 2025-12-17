from sqlalchemy import Column, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database import Base

class ProductionLineMachine(Base):
    """
    Intermediate table for N:N relationship between ProductionLine and Machine.
    A production line can have multiple machines, and a machine can be in multiple production lines.
    """
    __tablename__ = "production_line_machine"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    production_line_id = Column(Integer, ForeignKey("production_line.id", ondelete="CASCADE"), nullable=False)
    machine_id = Column(Integer, ForeignKey("machine.id"), nullable=False)
    
    # Relationships
    production_line = relationship("ProductionLine", back_populates="machines")
    machine = relationship("Machine", back_populates="production_lines")
    
    # Constraint: a machine cannot be duplicated in the same production line
    __table_args__ = (
        UniqueConstraint('production_line_id', 'machine_id', name='uq_production_line_machine'),
    )













