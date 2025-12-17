from sqlalchemy import Column, Integer, ForeignKey, DECIMAL
from sqlalchemy.orm import relationship
from app.database import Base

class ProductComposition(Base):
    __tablename__ = "composicao_produto"

    id = Column(Integer, primary_key=True, index=True)
    produto_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    materia_prima_id = Column(Integer, ForeignKey("materia_prima.id"), nullable=False)
    quantidade = Column(DECIMAL, nullable=False)

    produto = relationship("Product", foreign_keys=[produto_id], back_populates="compositions")
    materia_prima = relationship("RawMaterial", foreign_keys=[materia_prima_id])
