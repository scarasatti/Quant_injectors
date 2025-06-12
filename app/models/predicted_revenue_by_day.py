from sqlalchemy import Column, Integer, Float, Date, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

class PredictedRevenueByDay(Base):
    __tablename__ = "predicted_revenue_by_day"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("production_schedule_run.id"))

    billing_date = Column(Date)
    revenue_total = Column(Float)

    run = relationship("ProductionScheduleRun", back_populates="revenue_forecast")
