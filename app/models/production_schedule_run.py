from sqlalchemy import Column, Integer, Float, String, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class ProductionScheduleRun(Base):
    __tablename__ = "production_schedule_run"

    id = Column(Integer, primary_key=True, index=True)
    sequencing_start = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    setup_count = Column(Integer)
    optimized_setups = Column(Integer)
    on_time_jobs = Column(Integer)

    total_machine_hours = Column(Float)
    max_deadline_hours = Column(Float)
    machine_status = Column(String)

    results = relationship("ProductionScheduleResult", back_populates="run", cascade="all, delete-orphan")
    revenue_forecast = relationship("PredictedRevenueByDay", back_populates="run", cascade="all, delete-orphan")
