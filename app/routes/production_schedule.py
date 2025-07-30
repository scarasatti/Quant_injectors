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
from datetime import datetime, timedelta, date
from app.auth.auth_bearer import get_current_user
from app.models.job import Job
from app.models.user import User
router = APIRouter(prefix="/production-schedule", tags=["Production Schedule"])


@router.post("", response_model=ProductionScheduleRunResponse)
def create_schedule(
    run_data: ProductionScheduleRunCreate,
    results: List[ProductionScheduleResultCreate],
    revenue_by_day: List[PredictedRevenueByDayCreate],
    db: Session = Depends(get_db)
):
    print("==== INICIANDO CRIAÇÃO DO SCHEDULE ====")
    print(f"Recebidos: {len(results)} resultados | {len(revenue_by_day)} previsões de receita")

    run = ProductionScheduleRun(**run_data.dict(), created_at=datetime.utcnow())
    db.add(run)
    db.flush()

    for r in results:
        job = db.query(Job).filter_by(id=r.job_id).first()
        if not job:
            raise HTTPException(status_code=400, detail=f"Job ID {r.job_id} not found.")

        # Corrigir hora caso venha incompleta (HH:MM)
        hora_padronizada = r.completion_time
        if len(hora_padronizada.split(":")) == 2:
            hora_padronizada += ":00"

        try:
            actual_datetime = datetime.strptime(f"{r.actual_date} {hora_padronizada}", "%Y-%m-%d %H:%M:%S")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Erro ao interpretar horário de conclusão para job {r.job_id}: {str(e)}")

        scheduled_datetime = datetime.strptime(f"{r.scheduled_date} 23:59:59", "%Y-%m-%d %H:%M:%S")

        status = "On Time" if actual_datetime <= scheduled_datetime else "Late"
        billing_date = actual_datetime.date() + timedelta(days=3)
        expected_revenue = round(job.demand * job.product_value, 2)

        # DEBUG PRINT
        print("======= STATUS DEBUG =======")
        print(f"JOB ID           : {r.job_id}")
        print(f"Cliente          : {job.client.name}")
        print(f"Produto          : {job.product.name}")
        print(f"Data Agendada    : {scheduled_datetime}")
        print(f"Data de Entrega  : {actual_datetime}")
        print(f"Status Calculado : {status}")
        print("============================")

        result = ProductionScheduleResult(
            run_id=run.id,
            job_id=r.job_id,
            order_index=r.ordem,
            client_name=job.client.name,
            product_name=job.product.name,
            quantity=job.demand,
            scheduled_date=scheduled_datetime.date(),
            actual_date=actual_datetime.date(),
            completion_time=actual_datetime.time(),
            billing_date=billing_date,
            status=status,
            expected_revenue=expected_revenue
        )
        db.add(result)

    for rev in revenue_by_day:
        revenue = PredictedRevenueByDay(
            run_id=run.id,
            day=rev.day,
            expected_revenue=rev.expected_revenue
        )
        db.add(revenue)

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

