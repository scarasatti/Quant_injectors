from pulp import LpMinimize, LpProblem, LpVariable, lpSum, LpBinary, value
import numpy as np

# -------------------------------
# DADOS
# -------------------------------

n = 12  # número de jobs
m = 3   # número de máquinas

jobs = list(range(1, n + 1))
jobs0 = [0] + jobs  # inclui job fictício 0

# P[i][k] = tempo de processamento do job i na máquina k (1-indexado)
P = [[0]*m] + [
    [70, 70, 70],
    [28, 28, 28],
    [88, 88, 88],
    [67, 67, 67],
    [45, 45, 45],
    [117, 117, 117],
    [42, 42, 42],
    [115, 115, 115],
    [104, 104, 104],
    [64, 64, 64],
    [92, 92, 92],
    [69, 69, 69],
]

# S[i][j] = tempo de setup entre i e j (0 incluso)
S = np.zeros((n+1, n+1), dtype=int)
setup_original = [
    [0,1,1,1,1,1,1,1,1,1,1,0],
    [1,0,1,0,1,1,1,1,1,1,1,1],
    [1,1,0,1,1,0,1,1,1,0,1,1],
    [1,0,1,0,1,1,1,1,1,1,1,1],
    [1,1,1,1,0,1,1,0,1,1,1,1],
    [1,1,0,1,1,0,1,1,1,0,1,1],
    [1,1,1,1,1,1,0,1,0,1,0,1],
    [1,1,1,1,0,1,1,0,1,1,1,1],
    [1,1,1,1,1,1,0,1,0,1,0,1],
    [1,1,0,1,1,0,1,1,1,0,1,1],
    [1,1,1,1,1,1,0,1,0,1,0,1],
    [0,1,1,1,1,1,1,1,1,1,1,0],
]
for i in range(n):
    for j in range(n):
        S[i+1][j+1] = setup_original[i][j]

# d[j] = prazo do job j
d = [0, 144,144,144,240,240,240,240,480,480,792,792,792]
# R[j] = prioridade do job j
R = [0, 2,2,2,3,3,3,3,1,1,2,2,2]

# -------------------------------
# MODELO
# -------------------------------

model = LpProblem("Sequenciamento_Maquinas_Paralelo", LpMinimize)
M = 100000

# VARIÁVEIS
C = LpVariable.dicts("C", ((j, k) for j in jobs for k in range(1, m+1)), lowBound=0)
x = LpVariable.dicts("x", ((i, j, k) for i in jobs0 for j in jobs if i != j for k in range(1, m+1)), cat=LpBinary)
T = LpVariable.dicts("T", jobs, lowBound=0)

# OBJETIVO
model += lpSum(R[j] * T[j] for j in jobs)

# -------------------------------
# RESTRIÇÕES
# -------------------------------

# (1) Cada job deve ser precedido por exatamente um job (em alguma máquina)
for j in jobs:
    model += lpSum(x[i, j, k] for i in jobs0 if i != j for k in range(1, m+1)) == 1

# (2) Cada job precede no máximo um outro por máquina
for k in range(1, m+1):
    for i in jobs0:
        model += lpSum(x[i, j, k] for j in jobs if i != j) <= 1

# (3) Fluxo de entrada = saída (somente se i ≠ j)
for k in range(1, m+1):
    for j in jobs:
        entrada = lpSum(x[i, j, k] for i in jobs0 if i != j)
        saida = lpSum(x[j, h, k] for h in jobs if h != j)
        model += entrada - saida == 0

# (4) Precedência temporal com setup e processamento
for k in range(1, m+1):
    for i in jobs0:
        for j in jobs:
            if i != j:
                pij = P[j][k-1]
                sij = S[i][j]
                if i == 0:
                    model += C[j, k] >= (sij + pij) * x[i, j, k]
                else:
                    model += C[j, k] >= C[i, k] - M + (sij + pij + M) * x[i, j, k]

# (5) Atraso Tj >= Cjk - dj para todo j, k
for j in jobs:
    for k in range(1, m+1):
        model += T[j] >= C[j, k] - d[j]

# -------------------------------
# SOLUÇÃO
# -------------------------------

model.solve()

# -------------------------------
# RESULTADO
# -------------------------------

print("Status:", model.status)
print("Valor ótimo:", value(model.objective))
for j in jobs:
    for k in range(1, m+1):
        cjk = C[j, k].varValue
        if cjk is not None and cjk > 0.1:
            print(f"Job {j} → Máquina {k} | Fim: {cjk:.0f} | Atraso: {T[j].varValue:.0f}")
