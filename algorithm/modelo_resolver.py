# modelo_resolver.py
from pulp import LpMinimize, LpProblem, LpVariable, lpSum, LpBinary, value
import numpy as np

def resolver_sequenciamento(processing_time, due_time, weight, setup_time):
    jobs = list(range(len(processing_time)))
    model = LpProblem("Sequenciamento_Producao", LpMinimize)

    start = LpVariable.dicts("inicio", jobs, lowBound=0)
    early = LpVariable.dicts("antecipacao", jobs, lowBound=0)
    tardy = LpVariable.dicts("atraso", jobs, lowBound=0)
    x = LpVariable.dicts("setup", [(i, j) for i in jobs for j in jobs if i != j], cat=LpBinary)

    model += lpSum(weight[i] * tardy[i] for i in jobs)

    M = 10000
    for i in jobs:
        for j in jobs:
            if i != j:
                model += start[j] - start[i] - (M + setup_time[i][j]) * x[(i, j)] >= processing_time[i] - M
                model += x[(i, j)] + x[(j, i)] == 1

    for i in jobs:
        model += start[i] + processing_time[i] - tardy[i] + early[i] == due_time[i]

    model.solve()

    resultado = sorted(
        [{"job": i + 1, "inicio": round(value(start[i]), 2)} for i in jobs],
        key=lambda j: j["inicio"]
    )
    return resultado
