## Como rodar o servidor localmente

1. Instale as dependências:
    pip install -r requirements.txt

2. Suba o servidor:
uvicorn main:app --reload

3. Acesse a documentação automática:
    http://localhost:8000/docs

4. print(f"Job {int(job_index) + 1} - {job.name}")
    print("====================INPUTS DO JOB=====================")
    print(f"   Início sequenciamento       : {sequencing_date}")
    print(f"   Fator disponibilidade       : {available_factor:.2f}")
    print(f"   Cliente                     : {job.client.name} (Prioridade: {weight[job_index]})")
    print(f"   Produto                     : {job.product.name}")
    print(f"   Data prometida              : {promised_date}")
    print(f"   Ciclo                       : {job.product.cycle}")
    print(f"   Demanda                     : {job.demand}")
    print(f"   Gargalo (s)                 : {int(job.product.bottleneck)}")
    print(f"   Refugo (%)                  : {scrap_percent}%")
    print("====================INPUTS NO SOLVER=====================")
    print(f"   Demanda com refugo          : {int(demand_with_scrap)}".replace(",", "."))
    print(f"   Tempo no gargalo            : {cycle_bottleneck}")
    print(f"   Tempo total no Gargalo (s)  : {in_bottleneck_time}")
    print(f"   Tempo Total no Gargalo (h)  : {in_bottleneck_time /3600}")
    print(f"   Tempo pós Gargalo (s)       : {post_bottleneck_time}")
    print(f"   Tempo total pós gargalo (s) : {total_bottleneck_time}")
    print(f"   Tempo total pós gargalo (h) : {total_bottleneck_time /3600}")
    print(f"   Prazo    (h)                : {deadline}")
    print(f"   Prazo no gargalo (h)        : {deadline_in_bottleneck}")
    print(f"   Tempo total no gargalo      : {in_bottleneck_time_hours}")
