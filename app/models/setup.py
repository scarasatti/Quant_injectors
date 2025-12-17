from sqlalchemy import Column, Integer, String, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database import Base

class Setup(Base):
    """
    Setup representa o tempo de troca entre composition lines (molde + produto) em uma linha de produção.
    Baseado no modelo injetoras_modelo.py, onde setup é (i, j) -> tempo:
    - i = composition_line origem (molde + produto)
    - j = composition_line destino (molde + produto)
    
    Cada linha de produção gera uma matriz de setup composta por todos os produtos
    nas suas composition lines.
    
    O nome do setup é a concatenação do nome do molde com o nome do produto.
    Exemplo: "M1 Pote Turim Verde", "M2 Tampa Turim"
    
    Exemplo: M1-pote_turim para M2-tampa_turim = 60 minutos
             M1-pote_turim para M1-pote_turim = 0 minutos (mesmo molde, mesmo produto)
    """
    __tablename__ = "setup"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    production_line_id = Column(Integer, ForeignKey("production_line.id"), nullable=False)
    from_composition_line_id = Column(Integer, ForeignKey("composition_line.id"), nullable=False)
    to_composition_line_id = Column(Integer, ForeignKey("composition_line.id"), nullable=False)
    
    name = Column(String, nullable=False)  # Nome: concatenação de mold.name + product.name (do from_composition_line)
    setup_time = Column(Integer, nullable=False)  # Tempo em segundos

    # Relationships
    production_line = relationship("ProductionLine", back_populates="setups")
    from_composition_line = relationship("CompositionLine", foreign_keys=[from_composition_line_id], back_populates="setups_from")
    to_composition_line = relationship("CompositionLine", foreign_keys=[to_composition_line_id], back_populates="setups_to")
    
    # Constraint: não pode ter setup duplicado para a mesma combinação (production_line, from, to)
    __table_args__ = (
        UniqueConstraint('production_line_id', 'from_composition_line_id', 'to_composition_line_id',
                        name='uq_setup_production_line'),
    )
