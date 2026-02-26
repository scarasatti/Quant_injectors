from sqlalchemy import Column, Integer, Float, String, Date, Time, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

class ProductionScheduleResult(Base):
    __tablename__ = "production_schedule_result"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("production_schedule_run.id"))

    job_id = Column(Integer)
    order_number = Column(String)
    order_index = Column(Integer)
    production_line_id = Column(Integer)
    machine_id = Column(Integer)
    sequence_pos = Column(Integer)
    job_index_solver = Column(Integer)

    client_name = Column(String)
    order_number = Column(String)
    product_name = Column(String)
    machine_name = Column(String)
    mold_name = Column(String)
    quantity = Column(Integer)

    scheduled_date = Column(Date)
    scheduled_time = Column(Time)  # Hora limite prometida (Data Limite + Horário Limite de Faturamento)
    actual_date = Column(Date)
    actual_time = Column(Time)  # Hora real de início no gargalo
    start_in_bottleneck_hours = Column(Float)  # Horas desde sequencing_start até início no gargalo
    completion_date = Column(Date)
    completion_time = Column(Time)
    completion_time_hours = Column(Float)  # Fim do solver (valor bruto em horas)
    completion_injection_date = Column(Date)  # Data de finalização na injetora (sem pós)
    completion_injection_time = Column(Time)  # Hora de finalização na injetora (sem pós)
    billing_date = Column(Date)

    status = Column(String)
    expected_revenue = Column(Float)
    final_completion_time_hours = Column(Float)  # Tempo total: completion + post-injection

    run = relationship("ProductionScheduleRun", back_populates="results")
