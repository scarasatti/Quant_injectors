"""
Calculador de Matriz de Setup para o Solver de Sequenciamento.

Este módulo é responsável por construir a matriz de setup tridimensional {(i, j, k): tempo}
baseada nos produtos dos jobs e nas regras específicas do Job 0 (dummy) que representa
o estado atual das máquinas (state_machine).

Regras principais:
1. Setup é baseado nos PRODUTOS dos jobs (através das composition_lines)
2. Job 0 representa o produto que já está rodando em cada máquina (state_machine)
3. Cada máquina tem seu próprio produto inicial (do state_machine dela)
4. Setup 0 → j na máquina k = setup do produto inicial da máquina k para o produto do job j
"""

from typing import Dict, List, Tuple
from pathlib import Path
from datetime import datetime
from sqlalchemy.orm import Session, joinedload

from app.models.composition_line import CompositionLine
from app.models.setup import Setup
from app.models.mold import Mold
from app.models.product import Product


def build_setup_matrix(
    ordered_jobs: List[Dict],
    machine_id_to_idx: Dict[int, int],
    db: Session
) -> Dict[Tuple[int, int, int], float]:
    """
    Constrói a matriz de setup para o solver baseada nos PRODUTOS dos jobs.
    
    Args:
        ordered_jobs: Lista de jobs ordenados (dummy, excel, state_machine, programmed_stops)
        machine_id_to_idx: Mapeamento de machine_id real para índice usado no solver
        db: Sessão do banco de dados
    
    Retorna:
        {(i, j, k): tempo} onde:
        - i = job índice origem
        - j = job índice destino
        - k = máquina índice (1, 2, 3, ...)
        - tempo = setup_time em horas (convertido de MINUTOS do BD)
    
    REGRAS IMPORTANTES:
    1. Setup é baseado nos PRODUTOS dos jobs (através das composition_lines)
    2. Job 0 (dummy) representa o produto que já está rodando em cada máquina
    3. Cada máquina k tem seu próprio produto inicial (do state_machine dela)
    4. Setup 0 → j na máquina k = setup do produto inicial da máquina k para o produto do job j
    5. Jobs do Excel e state_machine mapeados têm setup real
    6. Jobs programmed_stops têm setup = 0 (não representam produtos)
    """
    
    # Criar diretório de logs
    base_dir = Path(__file__).resolve().parents[3]
    log_dir = base_dir / "logs" / "setup_matrix"
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    
    setup_matrix = {}
    
    # Separar jobs do Excel (que têm produtos reais) e criar mapeamento
    job_idx_to_comp_line = {}
    production_line_id = None
    state_machine_debug_info = {"mapped": [], "not_mapped": []}
    
    # Buscar composition_line_id para jobs que já têm (Excel)
    for job_data in ordered_jobs:
        j_idx = job_data["job_index"]
        comp_line_id = job_data.get("composition_line_id")
        if comp_line_id:
            job_idx_to_comp_line[j_idx] = comp_line_id
            # Buscar production_line_id da primeira composition_line encontrada
            if production_line_id is None:
                comp_line = db.query(CompositionLine).filter(CompositionLine.id == comp_line_id).first()
                if comp_line:
                    production_line_id = comp_line.production_line_id
    
    # Buscar composition_line_id para jobs de state_machine que têm mold_name e product_name
    # Esses jobs DEVEM ter setup baseado em seus produtos
    if production_line_id is None:
        # Tentar obter de algum state_machine job
        for job_data in ordered_jobs:
            if job_data.get("type") == "state_machine":
                mold_name = job_data.get("mold_name")
                product_name = job_data.get("product_name")
                
                if mold_name and product_name:
                    mold = db.query(Mold).filter(Mold.name.ilike(str(mold_name).strip())).first()
                    if not mold:
                        mold = db.query(Mold).filter(Mold.name.ilike(f"%{str(mold_name).strip()}%")).first()
                    
                    product = db.query(Product).filter(Product.name.ilike(str(product_name).strip())).first()
                    if not product:
                        product = db.query(Product).filter(Product.name.ilike(f"%{str(product_name).strip()}%")).first()
                    
                    if mold and product:
                        comp_line = (
                            db.query(CompositionLine)
                            .filter(
                                CompositionLine.mold_id == mold.id,
                                CompositionLine.product_id == product.id
                            )
                            .first()
                        )
                        if comp_line:
                            production_line_id = comp_line.production_line_id
                            break
    
    # Processar TODOS os state_machine jobs para mapear composition_line_id
    if production_line_id:
        for job_data in ordered_jobs:
            j_idx = job_data["job_index"]
            job_type = job_data.get("type")
            
            # Se já tem composition_line_id, pular
            if j_idx in job_idx_to_comp_line:
                continue
            
            # Se é state_machine, OBRIGATORIAMENTE buscar composition_line
            if job_type == "state_machine":
                mold_name = job_data.get("mold_name")
                product_name = job_data.get("product_name")
                
                # Se não tem mold_name ou product_name, registrar erro
                if not mold_name or not product_name:
                    missing = []
                    if not mold_name:
                        missing.append("mold_name")
                    if not product_name:
                        missing.append("product_name")
                    state_machine_debug_info["not_mapped"].append(
                        (j_idx, mold_name, product_name, f"Faltam: {', '.join(missing)}")
                    )
                    continue
                
                # Normalizar nomes
                mold_name_clean = str(mold_name).strip()
                product_name_clean = str(product_name).strip()
                
                # Buscar mold
                mold = db.query(Mold).filter(Mold.name.ilike(mold_name_clean)).first()
                if not mold:
                    mold = db.query(Mold).filter(Mold.name.ilike(f"%{mold_name_clean}%")).first()
                
                # Buscar product
                product = db.query(Product).filter(Product.name.ilike(product_name_clean)).first()
                if not product:
                    product = db.query(Product).filter(Product.name.ilike(f"%{product_name_clean}%")).first()
                
                # Se encontrou ambos, buscar composition_line
                if mold and product:
                    comp_line = (
                        db.query(CompositionLine)
                        .filter(
                            CompositionLine.production_line_id == production_line_id,
                            CompositionLine.mold_id == mold.id,
                            CompositionLine.product_id == product.id
                        )
                        .first()
                    )
                    
                    if comp_line:
                        job_idx_to_comp_line[j_idx] = comp_line.id
                        state_machine_debug_info["mapped"].append(
                            (j_idx, comp_line.id, mold_name_clean, product_name_clean)
                        )
                    else:
                        error_msg = f"CompositionLine não encontrada para mold_id={mold.id}, product_id={product.id}"
                        state_machine_debug_info["not_mapped"].append(
                            (j_idx, mold_name_clean, product_name_clean, error_msg)
                        )
                else:
                    missing = []
                    if not mold:
                        missing.append(f"mold '{mold_name_clean}'")
                    if not product:
                        missing.append(f"product '{product_name_clean}'")
                    state_machine_debug_info["not_mapped"].append(
                        (j_idx, mold_name_clean, product_name_clean, f"Não encontrado: {', '.join(missing)}")
                    )
    
    # Se não há jobs com composition_line_id, retornar matriz zerada
    if not job_idx_to_comp_line or production_line_id is None:
        jobs = [j["job_index"] for j in ordered_jobs]
        machines = sorted(machine_id_to_idx.values())
        for i in jobs:
            for j in jobs:
                for k in machines:
                    setup_matrix[(i, j, k)] = 0.0
        return setup_matrix
    
    # Buscar TODOS os setups da linha de produção
    all_setups = (
        db.query(Setup)
        .filter(Setup.production_line_id == production_line_id)
        .all()
    )
    
    # Criar cache: (from_comp_line_id, to_comp_line_id) -> setup_time em horas
    setup_cache = {}
    for setup in all_setups:
        key = (setup.from_composition_line_id, setup.to_composition_line_id)
        # Converter de MINUTOS para HORAS
        setup_cache[key] = setup.setup_time / 60.0
    
    # Identificar jobs de state_machine e produto inicial por máquina (para Job 0)
    state_machine_job_indices = set()
    initial_comp_line_by_machine_idx: Dict[int, int] = {}  # {machine_idx: comp_line_id}
    
    for job_data in ordered_jobs:
        if job_data.get("type") == "state_machine":
            j_idx = job_data["job_index"]
            state_machine_job_indices.add(j_idx)
            comp_line_id = job_idx_to_comp_line.get(j_idx)
            used_machine_idx = job_data.get("used_machine_idx")
            if comp_line_id and used_machine_idx:
                # O produto atual da máquina k (para Job 0 naquela máquina)
                initial_comp_line_by_machine_idx[used_machine_idx] = comp_line_id
    
    # Montar matriz para TODOS os jobs
    jobs = [j["job_index"] for j in ordered_jobs]
    machines = sorted(machine_id_to_idx.values())
    
    setups_found = 0
    setups_not_found = []
    
    for i in jobs:
        for j in jobs:
            for k in machines:
                # REGRA 1: Job 0 → Job 0 sempre zero
                if i == 0 and j == 0:
                    setup_matrix[(i, j, k)] = 0.0
                
                # REGRA 2: Setup do dummy (0 → j)
                # O Job 0 representa o produto inicial da máquina k (do state_machine)
                elif i == 0 and j != 0:
                    from_comp_line_id = initial_comp_line_by_machine_idx.get(k)
                    to_comp_line_id = job_idx_to_comp_line.get(j)
                    
                    if from_comp_line_id and to_comp_line_id:
                        if from_comp_line_id == to_comp_line_id:
                            # Mesmo produto, setup = 0
                            setup_matrix[(i, j, k)] = 0.0
                        else:
                            # Buscar setup do produto inicial da máquina k para o produto do job j
                            key = (from_comp_line_id, to_comp_line_id)
                            if key in setup_cache:
                                setup_matrix[(i, j, k)] = setup_cache[key]
                                setups_found += 1
                            else:
                                setup_matrix[(i, j, k)] = 0.0
                                if k == machines[0] and (i, j) not in [x[:2] for x in setups_not_found]:
                                    setups_not_found.append((i, j, from_comp_line_id, to_comp_line_id))
                    else:
                        # Máquina k não tem state_machine ou job j não tem produto
                        setup_matrix[(i, j, k)] = 0.0
                
                # REGRA 3: Setup reverso (j → 0)
                elif j == 0 and i != 0:
                    from_comp_line_id = job_idx_to_comp_line.get(i)
                    to_comp_line_id = initial_comp_line_by_machine_idx.get(k)
                    
                    if from_comp_line_id and to_comp_line_id:
                        if from_comp_line_id == to_comp_line_id:
                            setup_matrix[(i, j, k)] = 0.0
                        else:
                            key = (from_comp_line_id, to_comp_line_id)
                            if key in setup_cache:
                                setup_matrix[(i, j, k)] = setup_cache[key]
                                setups_found += 1
                            else:
                                setup_matrix[(i, j, k)] = 0.0
                    else:
                        setup_matrix[(i, j, k)] = 0.0
                
                # REGRA 4: Jobs normais entre si (ambos têm composition_line)
                elif i in job_idx_to_comp_line and j in job_idx_to_comp_line:
                    from_comp_line_id = job_idx_to_comp_line[i]
                    to_comp_line_id = job_idx_to_comp_line[j]
                    
                    if from_comp_line_id == to_comp_line_id:
                        # Mesmo produto = setup zero
                        setup_matrix[(i, j, k)] = 0.0
                    else:
                        key = (from_comp_line_id, to_comp_line_id)
                        if key in setup_cache:
                            setup_matrix[(i, j, k)] = setup_cache[key]
                            setups_found += 1
                        else:
                            setup_matrix[(i, j, k)] = 0.0
                            if k == machines[0] and (i, j) not in [x[:2] for x in setups_not_found]:
                                setups_not_found.append((i, j, from_comp_line_id, to_comp_line_id))
                
                # REGRA 5: Jobs sem composition_line (programmed_stops) = setup zero
                else:
                    setup_matrix[(i, j, k)] = 0.0
    
    # GERAR LOG DETALHADO
    log_file = log_dir / f"setup_matrix_PL{production_line_id}_{timestamp_str}.txt"
    
    with open(log_file, "w", encoding="utf-8") as f:
        f.write("=" * 100 + "\n")
        f.write(f"LOG DA MATRIZ DE SETUP - Linha de Produção {production_line_id}\n")
        f.write(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 100 + "\n\n")
        
        # 1. Resumo
        f.write("1. RESUMO\n")
        f.write("-" * 100 + "\n")
        f.write(f"Total de jobs: {len(jobs)}\n")
        f.write(f"Total de máquinas: {len(machines)}\n")
        f.write(f"Tamanho da matriz: {len(setup_matrix)} entradas ({len(jobs)} × {len(jobs)} × {len(machines)})\n")
        f.write(f"Setups encontrados no BD: {setups_found}\n")
        f.write(f"Setups não encontrados: {len(setups_not_found)}\n")
        f.write("\n")
        
        # 2. Jobs Mapeados
        f.write("2. JOBS COM COMPOSITION LINE MAPEADA\n")
        f.write("-" * 100 + "\n")
        for j_idx, cl_id in sorted(job_idx_to_comp_line.items()):
            comp_line = db.query(CompositionLine).options(
                joinedload(CompositionLine.mold),
                joinedload(CompositionLine.product)
            ).filter(CompositionLine.id == cl_id).first()
            
            job_data = next((jd for jd in ordered_jobs if jd["job_index"] == j_idx), None)
            job_type = job_data.get("type", "unknown") if job_data else "unknown"
            
            if comp_line:
                f.write(f"  Job {j_idx} ({job_type}): CL {cl_id} = {comp_line.mold.name} + {comp_line.product.name}\n")
            else:
                f.write(f"  Job {j_idx} ({job_type}): CL {cl_id} (NÃO ENCONTRADO)\n")
        f.write("\n")
        
        # 3. State Machine Mapeamentos
        f.write("3. STATE MACHINE JOBS\n")
        f.write("-" * 100 + "\n")
        if state_machine_debug_info["mapped"]:
            f.write("✅ MAPEADOS (terão setup):\n")
            for j_idx, cl_id, mold_name, product_name in state_machine_debug_info["mapped"]:
                f.write(f"  Job {j_idx}: {mold_name} + {product_name} -> CL {cl_id}\n")
        if state_machine_debug_info["not_mapped"]:
            f.write("\n❌ NÃO MAPEADOS (setup = 0):\n")
            for j_idx, mold_name, product_name, reason in state_machine_debug_info["not_mapped"]:
                f.write(f"  Job {j_idx}: mold='{mold_name}', product='{product_name}' - {reason}\n")
        if not state_machine_debug_info["mapped"] and not state_machine_debug_info["not_mapped"]:
            f.write("  Nenhum state_machine job encontrado.\n")
        f.write("\n")
        
        # 4. Produto Inicial por Máquina (Job 0)
        f.write("4. PRODUTO INICIAL POR MÁQUINA (Job 0)\n")
        f.write("-" * 100 + "\n")
        if initial_comp_line_by_machine_idx:
            for m_idx, cl_id in sorted(initial_comp_line_by_machine_idx.items()):
                comp_line = db.query(CompositionLine).options(
                    joinedload(CompositionLine.mold),
                    joinedload(CompositionLine.product)
                ).filter(CompositionLine.id == cl_id).first()
                
                if comp_line:
                    f.write(f"  Máquina {m_idx}: CL {cl_id} = {comp_line.mold.name} + {comp_line.product.name}\n")
                else:
                    f.write(f"  Máquina {m_idx}: CL {cl_id} (NÃO ENCONTRADO)\n")
        else:
            f.write("  Nenhum produto inicial configurado (sem state_machine).\n")
        f.write("\n")
        
        # 5. Matriz de Setup - Valores Não-Zero
        f.write("5. MATRIZ DE SETUP (Valores NÃO-ZERO apenas)\n")
        f.write("-" * 100 + "\n")
        non_zero_setups = [(k, v) for k, v in setup_matrix.items() if v > 0.0001]
        
        if non_zero_setups:
            for machine in sorted(machines):
                machine_setups = [(i, j, v) for (i, j, k), v in non_zero_setups if k == machine]
                if machine_setups:
                    f.write(f"\nMáquina {machine}:\n")
                    for i, j, v in sorted(machine_setups):
                        # Buscar nomes dos produtos
                        i_cl = job_idx_to_comp_line.get(i)
                        j_cl = job_idx_to_comp_line.get(j)
                        
                        i_name = "Job0" if i == 0 else f"CL{i_cl}" if i_cl else f"Job{i}"
                        j_name = "Job0" if j == 0 else f"CL{j_cl}" if j_cl else f"Job{j}"
                        
                        f.write(f"  setup[{i}, {j}, {machine}] = {v:.4f}h  ({i_name} → {j_name})\n")
        else:
            f.write("  TODOS os setups são ZERO!\n")
        f.write("\n")
        
        # 6. Setups Não Encontrados
        if setups_not_found:
            f.write("6. SETUPS NÃO ENCONTRADOS NO BD\n")
            f.write("-" * 100 + "\n")
            for i, j, from_cl, to_cl in setups_not_found:
                from_comp = db.query(CompositionLine).options(
                    joinedload(CompositionLine.mold),
                    joinedload(CompositionLine.product)
                ).filter(CompositionLine.id == from_cl).first()
                
                to_comp = db.query(CompositionLine).options(
                    joinedload(CompositionLine.mold),
                    joinedload(CompositionLine.product)
                ).filter(CompositionLine.id == to_cl).first()
                
                from_name = f"{from_comp.mold.name} + {from_comp.product.name}" if from_comp else f"CL {from_cl}"
                to_name = f"{to_comp.mold.name} + {to_comp.product.name}" if to_comp else f"CL {to_cl}"
                
                f.write(f"  Job {i} → Job {j}: {from_name} → {to_name}\n")
            f.write(f"\nTotal: {len(setups_not_found)} combinações não encontradas\n")
            f.write("\n")
        
        f.write("=" * 100 + "\n")
    
    return setup_matrix

