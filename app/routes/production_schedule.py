from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from typing import List

from app.database import get_db
from app.models.production_schedule_run import ProductionScheduleRun
from app.models.production_schedule_result import ProductionScheduleResult
from app.models.predicted_revenue_by_day import PredictedRevenueByDay

from app.schemas.production_schedule_run_schema import ProductionScheduleRunCreate, ProductionScheduleRunResponse
from app.schemas.production_schedule_result_schema import ProductionScheduleResultCreate, ProductionScheduleResultResponse
from app.schemas.predicted_revenue_byday_schema import PredictedRevenueByDayCreate, PredictedRevenueByDayResponse
from app.auth.auth_bearer import get_current_user
from app.models.user import User
router = APIRouter(prefix="/production-schedule", tags=["Production Schedule"])


@router.post("", response_model=ProductionScheduleRunResponse)
def create_schedule(
    run_data: ProductionScheduleRunCreate,
    results: List[ProductionScheduleResultCreate],
    revenue_by_day: List[PredictedRevenueByDayCreate],
    db: Session = Depends(get_db)
):
    run = ProductionScheduleRun(**run_data.dict(), created_at=datetime.utcnow())
    db.add(run)
    db.flush()

    sequencing_start = run_data.sequencing_start  # datetime vindo do request

    for r in results:
        # Buscar job original para obter a data prometida e duração
        job = db.query(Job).filter_by(id=r.job_id).first()
        if not job:
            raise HTTPException(status_code=400, detail=f"Job ID {r.job_id} not found.")

        # Calcular horários reais
        start_time = sequencing_start + timedelta(hours=r.inicio_h)
        end_time = start_time + timedelta(hours=job.total_time_hours)

        # Calcular status com base na data prometida do job
        status = "On Time" if end_time.date() <= job.promised_date.date() else "Late"

        # Prever data de faturamento (exemplo: 3 dias após término real)
        billing_date = end_time.date() + timedelta(days=3)

        # Receita esperada
        expected_revenue = round(job.demand * job.product_value, 2)

        # Criar resultado ajustado
        result = ProductionScheduleResult(
            run_id=run.id,
            job_id=r.job_id,
            order_index=r.ordem,
            client_name=job.client.name,
            product_name=job.product.name,
            quantity=job.demand,
            scheduled_date=end_time.date(),  # data planejada (fim do job)
            actual_date=end_time.date(),  # data real
            completion_time=end_time.time(),
            billing_date=billing_date,
            status=status,
            expected_revenue=expected_revenue
        )

        db.add(result)

    for r in revenue_by_day:
        db.add(PredictedRevenueByDay(**r.dict(), run_id=run.id))

    db.commit()
    db.refresh(run)
    return run


@router.get("", response_model=List[ProductionScheduleRunResponse])
def list_runs(db: Session = Depends(get_db)):
    return db.query(ProductionScheduleRun).order_by(ProductionScheduleRun.created_at.desc()).all()

@router.get("/latest", response_model=ProductionScheduleRunResponse)
def get_latest_run(db: Session = Depends(get_db)):
    run = (
        db.query(ProductionScheduleRun)
        .order_by(ProductionScheduleRun.created_at.desc())
        .first()
    )
    if not run:
        raise HTTPException(status_code=404, detail="No executions found")
    return run

@router.get("/{run_id}", response_model=ProductionScheduleRunResponse)
def get_run(run_id: int, db: Session = Depends(get_db)):
    run = db.query(ProductionScheduleRun).filter_by(id=run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Execution not found")
    return run

@router.delete("/{run_id}")
def delete_run(run_id: int, db: Session = Depends(get_db)):
    run = db.query(ProductionScheduleRun).filter_by(id=run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Execution not found")

    db.query(ProductionScheduleResult).filter_by(run_id=run.id).delete()
    db.query(PredictedRevenueByDay).filter_by(run_id=run.id).delete()
    db.delete(run)
    db.commit()

    return {"message": "Execution and related data deleted successfully"}

