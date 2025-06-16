from sqlalchemy import Column, Integer, String, DECIMAL
from app.database import Base

class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    cycle = Column(Integer, nullable=False)
    bottleneck = Column(Integer, nullable=False)
    scrap = Column(DECIMAL, nullable=False)