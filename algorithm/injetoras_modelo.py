import pulp as pl
from collections import defaultdict
import itertools

# ======== INPUTS ========
DEFAULT_JOBS = [0, 1, 2, 3]
DEFAULT_MACHINES = [1, 2]
DEFAULT_PROCESSING = {
    (0, 1): 0.0,
    (0, 2): 0.0,
    (1, 1): 10.0,
    (1, 2): 11.0,
    (2, 1): 20.0,
    (2, 2): 18.0,
    (3, 1): 15.0,
    (3, 2): 16.0
}  # (j,k) -> tempo
DEFAULT_DUE = {
    0: 0.0,
    1: 10.0,
    2: 18.0,
    3: 24.0
}                # prazo[j]
DEFAULT_PRIORITY = {
    0: 0.0,
    1: 1.0,
    2: 2.0,
    3: 3.0
}      # prioridade[j]


DEFAULT_SETUP3 = {
    (0, 0, 1): 0.0, (0, 0, 2): 0.0, (0, 1, 1): 1.0, (0, 1, 2): 1.0,
    (0, 2, 1): 0.0, (0, 2, 2): 1.0, (0, 3, 1): 1.0, (0, 3, 2): 0.0,

    (1, 0, 1): 0.0, (1, 0, 2): 0.0, (1, 1, 1): 1.0, (1, 1, 2): 1.0,
    (1, 2, 1): 0.0, (1, 2, 2): 0.0, (1, 3, 1): 1.0, (1, 3, 2): 1.0,

    (2, 0, 1): 0.0, (2, 0, 2): 0.0, (2, 1, 1): 0.0, (2, 1, 2): 0.0,
    (2, 2, 1): 1.0, (2, 2, 2): 1.0, (2, 3, 1): 1.0, (2, 3, 2): 1.0,

    (3, 0, 1): 0.0, (3, 0, 2): 0.0, (3, 1, 1): 1.0, (3, 1, 2): 1.0,
    (3, 2, 1): 0.0, (3, 2, 2): 0.0, (3, 3, 1): 0.0, (3, 3, 2): 0.0
}          # (i,j,k) -> setup


def build_and_solve(
    jobs=None,
    machines=None,
    processing=None,
    due=None,
    priority=None,
    setup3=None,
    dummy=0,
):
    jobs = list(DEFAULT_JOBS if jobs is None else jobs)
    machines = list(DEFAULT_MACHINES if machines is None else machines)
    processing = dict(DEFAULT_PROCESSING if processing is None else processing)
    due = dict(DEFAULT_DUE if due is None else due)
    priority = dict(DEFAULT_PRIORITY if priority is None else priority)
    setup3 = dict(DEFAULT_SETUP3 if setup3 is None else setup3)
    # garantir chaves presentes
    for j in jobs:
        for k in machines:
            processing.setdefault((j, k), 0.0)
    for i in jobs:
        for j in jobs:
            for k in machines:
                setup3.setdefault((i, j, k), 0.0)

    # Big-M conservador
    total_proc = sum(max(processing[(j, k)] for k in machines) for j in jobs)
    max_setup = max(setup3.values()) if setup3 else 0.0
    M = total_proc + max_setup + 1000.0

    model = pl.LpProblem("Sequenciamento_Injetoras", pl.LpMinimize)

    termino = pl.LpVariable.dicts("termino", ((j, k) for j in jobs for k in machines), lowBound=0.0)
    atraso = pl.LpVariable.dicts("atraso", jobs, lowBound=0.0)
    precede = pl.LpVariable.dicts("precede", ((i, j, k) for i in jobs for j in jobs for k in machines), cat=pl.LpBinary)

    # objetivo: somatório prioridade(j)*atraso(j) para j != dummy
    model += pl.lpSum(priority[j] * atraso[j] for j in jobs if not (dummy is not None and j == dummy))

    # (1) cada j != dummy tem exatamente um predecessor em alguma máquina
    for j in jobs:
        if dummy is not None and j == dummy:
            continue
        model += pl.lpSum(precede[(i, j, k)] for i in jobs for k in machines) == 1, f"one_pred_{j}"

    # (2) por máquina, no máximo um job inicia após o dummy
    if dummy is not None:
        for k in machines:
            model += pl.lpSum(precede[(dummy, j, k)] for j in jobs if j != dummy) <= 1, f"start_at_m_{k}"

    # (3) conservação de fluxo por máquina
    for j in jobs:
        if dummy is not None and j == dummy:
            continue
        for k in machines:
            model += (
                pl.lpSum(precede[(i, j, k)] for i in jobs if i != j)
                - pl.lpSum(precede[(j, i, k)] for i in jobs if i != j)
            ) == 0, f"flow_{j}_{k}"

    # (4) ligação atraso
    for j in jobs:
        if dummy is not None and j == dummy:
            continue
        for k in machines:
            model += atraso[j] >= termino[(j, k)] - due.get(j, 0.0), f"tardiness_{j}_{k}"

    # (5) encadeamento temporal com setup3 e processamento
    for j in jobs:
        if dummy is not None and j == dummy:
            continue
        for i in jobs:
            for k in machines:
                model += termino[(j, k)] >= termino[(i, k)] - M + \
                         (setup3[(i, j, k)] + processing[(j, k)] + M) * precede[(i, j, k)], \
                         f"time_link_{i}_{j}_{k}"

    # (6) ancora dummy = 0
    if dummy is not None:
        for k in machines:
            model += termino[(dummy, k)] == 0, f"anchor_dummy_{k}"

    solver = pl.PULP_CBC_CMD(msg=False)
    model.solve(solver)

    status = pl.LpStatus[model.status]
    obj = pl.value(model.objective)

    # reconstruir sequências
    sequences = {}
    for k in machines:
        succ = defaultdict(list)
        pred_count = defaultdict(int)
        for i, j in itertools.product(jobs, jobs):
            if i == j:
                continue
            v = pl.value(precede[(i, j, k)])
            if v is not None and v > 0.5:
                succ[i].append(j)
                pred_count[j] += 1

        start_nodes = [dummy] if (dummy is not None) else [j for j in jobs if pred_count[j] == 0]
        if not start_nodes:
            start_nodes = [min(jobs)]
        seq = []
        visited = set()
        for s in start_nodes:
            cur = s
            while True:
                nexts = [x for x in succ.get(cur, []) if x not in visited]
                if not nexts:
                    break
                nxt = nexts[0]
                if nxt == cur:
                    break
                visited.add(nxt)
                seq.append(nxt)
                cur = nxt
        sequences[k] = seq

    completion = {(j, k): pl.value(termino[(j, k)]) for j in jobs for k in machines}
    tard = {j: pl.value(atraso[j]) for j in jobs}

    return status, obj, sequences, completion, tard

if __name__ == "__main__":
    status, obj, sequences, completion, tard = build_and_solve()
    print("Status:", status)
    print("(valor objetivo):", obj)
    for k, seq in sequences.items():
        print(f"Maquina {k}:", seq)
    print("Terminos:")
    for (j, k), t in sorted(completion.items()):
        print(f"  termino[{j},{k}] = {t}")
    print("Atrasos:")
    for j, a in sorted(tard.items()):
        print(f"  atraso[{j}] = {a}")
