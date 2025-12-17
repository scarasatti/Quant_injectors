from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from app.database import Base

class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    
    # N:N relationship with molds through intermediate table
    molds = relationship("MoldProduct", back_populates="product")
    
    # 1:N relationship with product compositions (raw materials) - CASCADE DELETE
    compositions = relationship("ProductComposition", back_populates="produto", cascade="all, delete-orphan", foreign_keys="ProductComposition.produto_id")
    
    # 1:N relationship with production times (a product can have multiple production times with different machines/molds)
    production_times = relationship("ProductionTime", back_populates="product", cascade="all, delete-orphan")
    
    # 1:N relationship with composition lines
    composition_lines = relationship("CompositionLine", back_populates="product", cascade="all, delete-orphan")