from pulp import LpProblem, LpMinimize, LpVariable, lpSum, LpBinary, value

def solve_colheita_model(Cij, tij, ai, bi, P, N, K, M=10000):
    model = LpProblem("Problema_da_Colheita", LpMinimize)

    # Índices: blocos reais vão de 1 a N
    nodes = list(range(N + 2))  # inclui 0 (início/usina) e N+1 (fim/usina)
    blocks = list(range(1, N + 1))
    colhedoras = list(range(1, K + 1))

    # Variáveis
    x = LpVariable.dicts("x", ((i, j, k) for i in nodes for j in nodes for k in colhedoras if i != j), cat=LpBinary)
    S = LpVariable.dicts("S", ((i, k) for i in nodes for k in colhedoras), lowBound=0)

    # Função objetivo
    model += lpSum(Cij[i][j] * x[i, j, k] for i in nodes for j in nodes for k in colhedoras if i != j) + \
             lpSum(0.000001 * S[i, k] for i in nodes for k in colhedoras)

    # Cada colhedora parte da usina no máximo uma vez
    for k in colhedoras:
        model += lpSum(x[0, j, k] for j in nodes if j != 0) == 1

    # Cada colhedora termina na usina
    for k in colhedoras:
        model += lpSum(x[i, N + 1, k] for i in nodes if i != N + 1) == 1

    # Cada bloco deve ser visitado uma única vez
    for i in blocks:
        model += lpSum(x[i, j, k] for j in nodes for k in colhedoras if i != j) == 1

    # Continuidade de fluxo
    for j in blocks:
        for k in colhedoras:
            model += lpSum(x[i, j, k] for i in nodes if i != j) == lpSum(x[j, l, k] for l in nodes if l != j)

    # Janela de tempo
    for i in blocks:
        for k in colhedoras:
            model += S[i, k] >= ai[i - 1]
            model += S[i, k] <= bi[i - 1]
            model += S[i, k] <= P

    # Sequenciamento com tempo de deslocamento
    for i in nodes:
        for j in nodes:
            if i != j:
                for k in colhedoras:
                    model += S[i, k] + tij[i][j] <= S[j, k] + (1 - x[i, j, k]) * M

    # Resolver o modelo
    model.solve()

    # Coletar solução
    rotas = [(i, j, k) for (i, j, k) in x if x[i, j, k].varValue == 1]
    tempos = {(i, k): value(S[i, k]) for (i, k) in S if value(S[i, k]) is not None and value(S[i, k]) > 0}

    return {
        "rotas": rotas,
        "tempos": tempos,
        "status": model.status
    }
