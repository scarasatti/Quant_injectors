from sqlalchemy import Column, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database import Base

class MoldProduct(Base):
    """
    Intermediate table for N:N relationship between Mold and Product.
    Represents which products can be manufactured by each mold.
    """
    __tablename__ = "mold_product"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    mold_id = Column(Integer, ForeignKey("mold.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    
    # Relationships
    mold = relationship("Mold", back_populates="products")
    product = relationship("Product", back_populates="molds")
    
    # Constraint: a product cannot be duplicated for the same mold
    __table_args__ = (
        UniqueConstraint('mold_id', 'product_id', name='uq_mold_product'),
    )

