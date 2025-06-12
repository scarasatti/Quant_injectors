from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from collections import defaultdict
from pulp import value

from app.models.production_schedule_run import ProductionScheduleRun
from app.models.production_schedule_result import ProductionScheduleResult
from app.models.predicted_revenue_by_day import PredictedRevenueByDay

def save_solver_result_to_db(
    db: Session,
    sequencing_date: datetime,
    jobs_data: list,
    ordem_execucao: list[int],
    start: dict,
    tardy: dict,
    processing_time: list,
    setup_count: int,
    optimized_setups: int
) -> ProductionScheduleRun:
    total_machine_hours = sum(processing_time)
    max_deadline_hours = max(
        (job.promised_date.replace(hour=12, minute=0, second=0, microsecond=0) - sequencing_date).total_seconds() / 3600
        for job in jobs_data
    )
    on_time_count = 0
    revenue_by_day = defaultdict(float)

    run = ProductionScheduleRun(
        sequencing_start=sequencing_date,
        setup_count=setup_count,
        optimized_setups=optimized_setups,
        on_time_jobs=0,
        total_machine_hours=round(total_machine_hours, 2),
        max_deadline_hours=round(max_deadline_hours, 2),
        machine_status="On Time" if total_machine_hours <= max_deadline_hours else "Late",
        created_at=datetime.utcnow()
    )
    db.add(run)
    db.flush()

    for pos, i in enumerate(ordem_execucao):
        job = jobs_data[i]
        start_h = value(start[i])
        tardy_h = value(tardy[i])
        proc_h = processing_time[i]

        start_dt = sequencing_date + timedelta(hours=start_h)
        end_dt = sequencing_date + timedelta(hours=start_h + proc_h)
        revenue = round(job.product_value * job.demand, 2)
        status = "On Time" if tardy_h == 0 else "Late"
        if tardy_h == 0:
            on_time_count += 1

        revenue_by_day[end_dt.date()] += revenue

        db.add(ProductionScheduleResult(
            run_id=run.id,
            job_id=job.id,
            order_index=pos,
            client_name=job.client.name,
            product_name=job.product.name,
            quantity=job.demand,
            scheduled_date=job.promised_date.date(),
            actual_date=start_dt.date(),
            completion_time=end_dt.time(),
            billing_date=end_dt.date(),
            status=status,
            expected_revenue=revenue
        ))

    run.on_time_jobs = on_time_count
    db.flush()

    for day, total in revenue_by_day.items():
        db.add(PredictedRevenueByDay(
            run_id=run.id,
            billing_date=day,
            revenue_total=round(total, 2)
        ))

    db.commit()
    return run
