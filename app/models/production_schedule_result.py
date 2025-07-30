from sqlalchemy import Column, Integer, Float, String, Date, Time, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

class ProductionScheduleResult(Base):
    __tablename__ = "production_schedule_result"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("production_schedule_run.id"))

    job_id = Column(Integer)
    order_index = Column(Integer)

    client_name = Column(String)
    product_name = Column(String)
    quantity = Column(Integer)

    scheduled_date = Column(Date)
    actual_date = Column(Date)
    completion_date = Column(Date)
    completion_time = Column(Time)
    billing_date = Column(Date)

    status = Column(String)
    expected_revenue = Column(Float)

    run = relationship("ProductionScheduleRun", back_populates="results")
