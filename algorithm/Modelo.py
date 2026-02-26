from pulp import LpMinimize, LpProblem, LpVariable, lpSum, LpBinary, PULP_CBC_CMD, value
import numpy as np

# Datas de referência (convertidas para dias)
DATA_INICIO = '2025-04-01 00:00:00'
DATA_FIM = '2025-12-10 00:00:00'
DIAS_TOTAIS = 254  # De 01/04 a 10/12 (253 dias + dia 0)

# Blocos (convertendo datas para dias relativos)
blocos_info = {
    1: {'colheita': 5, 'min': 35, 'max': 96},  # 05/05 a 05/07
    2: {'colheita': 7, 'min': 0, 'max': 254},  # Qualquer momento
    3: {'colheita': 3, 'min': 62, 'max': 254},  # 01/06 em diante (ajustado)
    4: {'colheita': 8, 'min': 0, 'max': 254}  # Qualquer momento
}

# Matriz de distâncias CORRETA (km)
dist_matrix = np.array([
    # 0    1    2    3    4    5   (nós)
    [0, 5, 3.8, 2.2, 2.4, 0],  # 0: Usina saída
    [5, 0, 2.6, 3.1, 5.1, 5],  # 1: Bloco 1
    [3.8, 2.6, 0, 1.6, 2.8, 3.8],  # 2: Bloco 2
    [2.2, 3.1, 1.6, 0, 2.3, 2.2],  # 3: Bloco 3
    [2.4, 5.1, 2.8, 2.3, 0, 2.4],  # 4: Bloco 4
    [0, 5, 3.8, 2.2, 2.4, 0]  # 5: Usina retorno
])

# Matriz de tempo de viagem CORRETA (dias)
# (Considerando 8h úteis/dia = 480 min/dia útil)
viagem_matrix = np.array([
    # 0     1     2     3     4     5   (nós)
    [0, 0.063, 0.048, 0.021, 0.023, 0],  # 0
    [0.063, 0, 0.027, 0.042, 0.065, 0.063],  # 1
    [0.048, 0.027, 0, 0.017, 0.029, 0.048],  # 2
    [0.021, 0.042, 0.017, 0, 0.023, 0.021],  # 3
    [0.023, 0.065, 0.029, 0.023, 0, 0.023],  # 4
    [0, 0.063, 0.048, 0.021, 0.023, 0]  # 5
])

# =================================================================================
# CONFIGURAÇÃO DO MODELO
# =================================================================================
N = 4  # 4 blocos
K = 2  # 2 colhedoras
P = DIAS_TOTAIS  # Prazo máximo em dias
M = 1000  # Big-M

nodes = [0, 1, 2, 3, 4, 5]  # 0=usina_saida, 1-4=blocos, 5=usina_retorno
blocks = [1, 2, 3, 4]
colhedoras = [1, 2]

# Arcos válidos (exclui movimentos impossíveis)
allowed_arcs = []
for i in nodes:
    for j in nodes:
        if i == j:
            continue
        if i == 5:  # Não sai da usina de retorno
            continue
        if j == 0:  # Não volta para usina de saída
            continue
        if i == 0 and j == 5:  # Não vai direto da saída para retorno
            continue
        allowed_arcs.append((i, j))

# =================================================================================
# CONSTRUÇÃO DO MODELO
# =================================================================================
model = LpProblem("Colheita_Otimizada", LpMinimize)

# Variáveis de decisão
x = LpVariable.dicts("x",
                     [(i, j, k) for (i, j) in allowed_arcs for k in colhedoras],
                     cat=LpBinary)

S = LpVariable.dicts("S",
                     [(i, k) for i in nodes for k in colhedoras],
                     lowBound=0)

# Função objetivo
model += lpSum(dist_matrix[i][j] * x[i, j, k]
               for (i, j) in allowed_arcs for k in colhedoras)

# Restrições
# 1. Cada colhedora sai da usina
for k in colhedoras:
    model += lpSum(x[0, j, k] for j in blocks) == 1

# 2. Cada colhedora retorna à usina
for k in colhedoras:
    model += lpSum(x[i, 5, k] for i in blocks) == 1

# 3. Cada bloco é colhido uma vez
for i in blocks:
    model += lpSum(x[i, j, k]
                   for j in nodes for k in colhedoras
                   if (i, j) in allowed_arcs) == 1

# 4. Conservação de fluxo
for h in blocks:
    for k in colhedoras:
        model += lpSum(x[i, h, k]
                       for i in nodes
                       if (i, h) in allowed_arcs) == \
                 lpSum(x[h, j, k]
                       for j in nodes
                       if (h, j) in allowed_arcs)

# 5. Janelas temporais
for i in blocks:
    for k in colhedoras:
        model += S[i, k] >= blocos_info[i]['min']
        model += S[i, k] <= blocos_info[i]['max']

# 6. Tempo de saída
for k in colhedoras:
    model += S[0, k] == 0

# 7. Prazo final
for k in colhedoras:
    model += S[5, k] <= P

# 8. Sequenciamento temporal
for (i, j) in allowed_arcs:
    for k in colhedoras:
        # Tempo de término no nó anterior
        termino_i = S[i, k] + (blocos_info[i]['colheita'] if i in blocks else 0)

        # Tempo de chegada no próximo nó
        chegada_j = termino_i + viagem_matrix[i][j]

        # Restrição de sequenciamento
        model += S[j, k] >= chegada_j

# =================================================================================
# RESOLUÇÃO E VISUALIZAÇÃO
# =================================================================================
model.solve(PULP_CBC_CMD(msg=True))


# Função para reconstruir rotas
def reconstruir_rota(k):
    rota = ["Usina(0)"]
    current = 0
    while current != 5:
        for j in nodes:
            if (current, j) in allowed_arcs and value(x[current, j, k]) > 0.5:
                if j == 5:
                    rota.append("Usina(5)")
                else:
                    rota.append(f"Bloco {j}")
                current = j
                break
    return " → ".join(rota)


# Resultados
print(f"Status: {model.status}")
print(f"Custo Total: {value(model.objective):.3f} km\n")

for k in colhedoras:
    rota = reconstruir_rota(k)
    print(f"Colhedora {k}: {rota}")
    for i in blocks:
        if value(S[i, k]) > 0:
            print(
                f"  Bloco {i}: Início={value(S[i, k]):.1f}d, Término={value(S[i, k]) + blocos_info[i]['colheita']:.1f}d")
    print(f"  Retorno à usina: {value(S[5, k]):.1f}d\n")