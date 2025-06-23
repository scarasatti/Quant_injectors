from sqlalchemy import Column, Integer, Float, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

class Setup(Base):
    __tablename__ = "setup"

    id = Column(Integer, primary_key=True, index=True)

    from_product = Column(Integer, ForeignKey("products.id"), nullable=False)
    to_product = Column(Integer, ForeignKey("products.id"), nullable=False)

    setup_time = Column(Integer, nullable=False)

    from_product_rel = relationship("Product", foreign_keys=[from_product])
    to_product_rel = relationship("Product", foreign_keys=[to_product])
