from sqlalchemy import Column, Integer, Float, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

class Setup(Base):
    __tablename__ = "setup"

    id = Column(Integer, primary_key=True, index=True)

    produto_de = Column(Integer, ForeignKey("products.id"), nullable=False)
    produto_para = Column(Integer, ForeignKey("products.id"), nullable=False)

    tempo_setup = Column(Integer, nullable=False)
    menor_produto = Column(Float, nullable=True)
    maior_produto = Column(Float, nullable=True)

    produto_de_rel = relationship("Product", foreign_keys=[produto_de])
    produto_para_rel = relationship("Product", foreign_keys=[produto_para])
