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
    post_bottleneck_times: list[float],
    setup_count: int,
    optimized_setups: int,
) -> ProductionScheduleRun:
    total_machine_hours = sum(processing_time)
    max_deadline_hours = max(
        (job.promised_date.replace(hour=12, minute=0, second=0, microsecond=0) - sequencing_date).total_seconds() / 3600
        for job in jobs_data
    )

    on_time_count = 0
    revenue_by_day = defaultdict(float)

    print("\n==== INICIANDO SALVAMENTO DO RESULTADO DO SOLVER ====")
    print(f"Sequencing start       : {sequencing_date}")
    print(f"Total machine hours    : {total_machine_hours}")
    print(f"Max deadline hours     : {max_deadline_hours}")
    print(f"Setup count            : {setup_count}")
    print(f"Optimized setups       : {optimized_setups}")
    print("------------------------------------------------------")

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
        proc_time = processing_time[i]
        post_bottleneck = post_bottleneck_times[i]

        # Calcula os momentos finais corretos com base no seu fluxo
        moment_conclusion = proc_time + start_h
        moment_conclusion_final = moment_conclusion + post_bottleneck
        production_completion = sequencing_date + timedelta(hours=moment_conclusion_final)

        start_dt = sequencing_date + timedelta(hours=start_h)

        # DEBUG COMPLETO PARA O STATUS
        print("\n=== AVALIAÇÃO DO STATUS DO JOB ===")
        print(f"Job ID                   : {job.id}")
        print(f"Cliente                  : {job.client.name}")
        print(f"Produto                  : {job.product.name}")
        print(f"Quantidade               : {job.demand}")
        print(f"Data Prometida Original  : {job.promised_date}")
        print(f"Hora da Promised Date    : {job.promised_date.time()}")
        print(f"Data Prometida Corrigida : {job.promised_date.replace(hour=12, minute=0, second=0, microsecond=0)}")
        print(f"Data Início Real         : {start_dt}")
        print(f"Duração Processo         : {proc_time} horas")
        print(f"Pós-Gargalo              : {post_bottleneck} horas")
        print(f"Conclusão Produção       : {production_completion}")
        print("=> Comparando: production_completion <= promised_date_corrigida ?")

        # Corrige a hora da promised_date para 12h
        promised_dt = job.promised_date.replace(hour=12, minute=0, second=0, microsecond=0)
        status = "On Time" if production_completion <= promised_dt else "Late"

        if status == "On Time":
            print(">> STATUS DEFINIDO: ON TIME ✅")
            on_time_count += 1
        else:
            print(">> STATUS DEFINIDO: LATE ❌")

        # Calcula e exibe billing date
        billing_date = production_completion.date() + timedelta(days=3)
        print(f"Billing Date Calculado   : {billing_date} (esperado: {production_completion.date()} + 3 dias)")

        revenue = round(job.product_value * job.demand, 2)
        revenue_by_day[billing_date] += revenue

        # PRINT FINAL DO JOB
        print("\n[JOB DEBUG FINAL]")
        print(f"Promised Date     : {job.promised_date}")
        print(f"Start (real)      : {start_dt}")
        print(f"End (real)        : {production_completion}")
        print(f"Status Calculado  : {status}")
        print(f"Billing Date      : {billing_date}")
        print(f"Expected Revenue  : {revenue}")
        print("------------------------------------------------------")

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

    print("\n==== FATURAMENTO PREVISTO POR DIA ====")
    for day, total in revenue_by_day.items():
        print(f"{day} => R$ {round(total, 2)}")
        db.add(PredictedRevenueByDay(
            run_id=run.id,
            billing_date=day,
            revenue_total=round(total, 2)
        ))

    print("\n==== SALVAMENTO CONCLUÍDO COM SUCESSO ====")
    db.commit()
    return run
