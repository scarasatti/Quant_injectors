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
    processing_time: list[float],
    bottleneck_times: list[float],
    setup_count: int,
    optimized_setups: int,
) -> ProductionScheduleRun:

    total_machine_hours = sum(processing_time)

    max_deadline_hours = max(
        value(start[i]) + processing_time[i] + bottleneck_times[i]
        for i in range(len(jobs_data))
    )

    machine_status = "On Time" if total_machine_hours >= max_deadline_hours else "Late"

    on_time_count = 0
    revenue_by_day = defaultdict(float)

    run = ProductionScheduleRun(
        sequencing_start=sequencing_date,
        setup_count=setup_count,
        optimized_setups=optimized_setups,
        on_time_jobs=0,
        total_machine_hours=int(total_machine_hours),
        max_deadline_hours=int(max_deadline_hours),
        machine_status=machine_status,
        created_at=datetime.utcnow()
    )
    db.add(run)
    db.flush()

    for pos, i in enumerate(ordem_execucao):
        job = jobs_data[i]
        start_h = value(start[i])
        proc_time = processing_time[i]
        bottleneck = bottleneck_times[i]

        moment_conclusion = start_h + proc_time
        moment_conclusion_final = moment_conclusion + bottleneck
        production_completion = sequencing_date + timedelta(hours=moment_conclusion_final)
        start_dt = sequencing_date + timedelta(hours=start_h)

        status = "On Time" if production_completion <= job.promised_date else "Late"
        if status == "On Time":
            on_time_count += 1

        billing_date = production_completion.date()
        revenue = round(job.product_value * job.demand, 2)
        revenue_by_day[billing_date] += revenue

        db.add(ProductionScheduleResult(
            run_id=run.id,
            job_id=job.id,
            order_index=pos,
            client_name=job.client.name,
            product_name=job.product.name,
            quantity=job.demand,
            scheduled_date=job.promised_date.date(),
            actual_date=start_dt.date(),
            completion_date=production_completion.date(),
            completion_time=production_completion.time(),
            billing_date=billing_date,
            status=status,
            expected_revenue=revenue
        ))

    run.on_time_jobs = on_time_count
    db.flush()

    for day, total in revenue_by_day.items():
        print(f"{day} => R$ {round(total, 2)}")
        db.add(PredictedRevenueByDay(
            run_id=run.id,
            billing_date=day,
            revenue_total=round(total, 2)
        ))

    db.commit()
    return run
