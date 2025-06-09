from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from app.database import Base

class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)

    promised_date = Column(DateTime)
    sequencing_start_date = Column(DateTime)

    total_time_sec = Column(Integer)
    demand = Column(Integer)
    total_time_hours = Column(Float)

    deadline_days = Column(Integer)
    deadline_hours = Column(Float)

    product_value = Column(Float)
    produzido = Column(Integer, default=0)

    fk_id_client = Column(Integer, ForeignKey("clients.id"))
    fk_id_product = Column(Integer, ForeignKey("products.id"))

    client = relationship("Client")
    product = relationship("Product")
