from pulp import LpMinimize, LpProblem, LpVariable, lpSum, LpBinary, value, PULP_CBC_CMD
import numpy as np

# -------------------------------
# DADOS
# -------------------------------

jobs = list(range(12))

due_time = [144, 144, 144, 240, 240, 240, 240, 480, 480, 792, 792, 792]
processing_time = [70, 28, 88, 67, 45, 117, 42, 115, 104, 64, 92, 69]
weight = [2, 2, 2, 3, 3, 3, 3, 1, 1, 2, 2, 2]

setup_time = np.array([
    [0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0],
    [1, 0, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1],
    [1, 1, 0, 1, 1, 0, 1, 1, 1, 0, 1, 1],
    [1, 0, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1],
    [1, 1, 1, 1, 0, 1, 1, 0, 1, 1, 1, 1],
    [1, 1, 0, 1, 1, 0, 1, 1, 1, 0, 1, 1],
    [1, 1, 1, 1, 1, 1, 0, 1, 0, 1, 0, 1],
    [1, 1, 1, 1, 0, 1, 1, 0, 1, 1, 1, 1],
    [1, 1, 1, 1, 1, 1, 0, 1, 0, 1, 0, 1],
    [1, 1, 0, 1, 1, 0, 1, 1, 1, 0, 1, 1],
    [1, 1, 1, 1, 1, 1, 0, 1, 0, 1, 0, 1],
    [0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0],
])

# -------------------------------
# MODELO
# -------------------------------

model = LpProblem("Sequenciamento_Produção_LINGO_EQUIVALENTE", LpMinimize)

start = LpVariable.dicts("inicio", jobs, lowBound=0)
early = LpVariable.dicts("antecipacao", jobs, lowBound=0)
tardy = LpVariable.dicts("atraso", jobs, lowBound=0)

x = LpVariable.dicts("setup", [(i, j) for i in jobs for j in jobs if i != j], cat=LpBinary)

# -------------------------------
# OBJETIVO
# -------------------------------
model += lpSum(weight[i] * tardy[i] for i in jobs)

# -------------------------------
# RESTRIÇÕES
# -------------------------------
M = 10000  # mesmo valor usado no LINGO

for i in jobs:
    for j in jobs:
        if i != j:
            model += start[j] - start[i] - (M + setup_time[i][j]) * x[(i, j)] >= processing_time[i] - M
            model += x[(i, j)] + x[(j, i)] == 1

for i in jobs:
    model += start[i] + processing_time[i] - tardy[i] + early[i] == due_time[i]

# -------------------------------
# RESOLUÇÃO
# -------------------------------
model.solve(PULP_CBC_CMD())

# -------------------------------
# RESULTADO
# -------------------------------
jobs_ordenados = sorted(jobs, key=lambda i: value(start[i]))
for i in jobs_ordenados:
    print(f"Job {i+1} | Início: {value(start[i]):.0f}")
