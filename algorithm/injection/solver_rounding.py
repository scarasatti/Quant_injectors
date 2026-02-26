"""
Utilitário para arredondar valores do solver para garantir consistência.
"""

from typing import Dict, Tuple


def round_solver_value(value: float, decimals: int = 1) -> float:
    """
    Arredonda um valor para o número especificado de casas decimais.
    
    Args:
        value: Valor a ser arredondado
        decimals: Número de casas decimais (padrão: 1 para compatibilidade com LINDO)
    
    Returns:
        Valor arredondado
    """
    return round(value, decimals)


def round_processing_matrix(
    processing: Dict[Tuple[int, int], float],
    decimals: int = 1
) -> Dict[Tuple[int, int], float]:
    """
    Arredonda todos os valores da matriz de processing.
    
    Args:
        processing: {(job, machine): tempo}
        decimals: Número de casas decimais
    
    Returns:
        Matriz arredondada
    """
    return {key: round(value, decimals) for key, value in processing.items()}


def round_due_dates(
    due: Dict[int, float],
    decimals: int = 1
) -> Dict[int, float]:
    """
    Arredonda todos os valores de deadline.
    
    Args:
        due: {job: deadline}
        decimals: Número de casas decimais
    
    Returns:
        Deadlines arredondados
    """
    return {key: round(value, decimals) for key, value in due.items()}


def round_setup_matrix(
    setup3: Dict[Tuple[int, int, int], float],
    decimals: int = 1
) -> Dict[Tuple[int, int, int], float]:
    """
    Arredonda todos os valores da matriz de setup.
    
    Args:
        setup3: {(i, j, k): tempo}
        decimals: Número de casas decimais
    
    Returns:
        Matriz arredondada
    """
    return {key: round(value, decimals) for key, value in setup3.items()}


def round_all_solver_inputs(
    solver_inputs: Dict,
    decimals: int = 1
) -> Dict:
    """
    Arredonda TODOS os valores numéricos dos inputs do solver.
    
    Args:
        solver_inputs: Dict com jobs, machines, processing, due, priority, setup3
        decimals: Número de casas decimais (1 = compatibilidade com LINDO)
    
    Returns:
        Inputs arredondados
    """
    rounded = {
        "jobs": solver_inputs["jobs"],  # Lista de inteiros, não precisa arredondar
        "machines": solver_inputs["machines"],  # Lista de inteiros
        "processing": round_processing_matrix(solver_inputs["processing"], decimals),
        "due": round_due_dates(solver_inputs["due"], decimals),
        "priority": solver_inputs["priority"],  # Inteiros, não precisa arredondar
        "setup3": round_setup_matrix(solver_inputs["setup3"], decimals),
    }
    
    # Preservar campos extras se existirem
    for key in solver_inputs:
        if key not in rounded:
            rounded[key] = solver_inputs[key]
    
    return rounded


# Configuração global
SOLVER_DECIMAL_PRECISION = 1  # Mudar aqui para ajustar globalmente

