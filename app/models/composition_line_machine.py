from sqlalchemy import Column, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database import Base

class CompositionLineMachine(Base):
    """
    Intermediate table for N:N relationship between CompositionLine and Machine.
    Cycle time is retrieved from ProductionTime table based on machine, product, and mold.
    """
    __tablename__ = "composition_line_machine"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    composition_line_id = Column(Integer, ForeignKey("composition_line.id"), nullable=False)
    machine_id = Column(Integer, ForeignKey("machine.id"), nullable=False)
    
    # Relationships
    composition_line = relationship("CompositionLine", back_populates="machines")
    machine = relationship("Machine", back_populates="composition_lines")
    
    # Constraint: a machine cannot be duplicated in the same composition line
    __table_args__ = (
        UniqueConstraint('composition_line_id', 'machine_id', name='uq_composition_line_machine'),
    )
