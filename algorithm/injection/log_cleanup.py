"""
Utilitário para limpeza automática de logs antigos.
Mantém apenas os N arquivos mais recentes de cada tipo.
"""

from pathlib import Path
from datetime import datetime
from typing import Dict, List
import os


def cleanup_old_logs(
    log_dir: Path,
    keep_recent: int = 5,
    log_patterns: Dict[str, int] = None
) -> Dict[str, int]:
    """
    Remove logs antigos, mantendo apenas os N mais recentes de cada tipo.
    
    Args:
        log_dir: Diretório onde estão os logs
        keep_recent: Número de arquivos mais recentes para manter (padrão: 5)
        log_patterns: Dict com padrões de nome e quantos manter para cada tipo.
                     Ex: {"excel_read_": 5, "setup_matrix_debug_": 3, "solver_": 5}
    
    Returns:
        Dict com estatísticas: {"deleted": X, "kept": Y, "by_type": {...}}
    """
    if not log_dir.exists():
        return {"deleted": 0, "kept": 0, "by_type": {}}
    
    # Padrões padrão se não especificados
    if log_patterns is None:
        log_patterns = {
            "excel_read_": keep_recent,
            "setup_matrix_debug_": keep_recent,
            "solver_inputs_": keep_recent,
            "solver_results_": keep_recent,
        }
    
    stats = {"deleted": 0, "kept": 0, "by_type": {}}
    
    # Agrupar arquivos por tipo (prefixo)
    files_by_type: Dict[str, List[Path]] = {}
    
    for file_path in log_dir.iterdir():
        if not file_path.is_file():
            continue
        
        filename = file_path.name
        
        # Identificar tipo pelo prefixo
        file_type = None
        for pattern in log_patterns.keys():
            if filename.startswith(pattern):
                file_type = pattern
                break
        
        if file_type:
            if file_type not in files_by_type:
                files_by_type[file_type] = []
            files_by_type[file_type].append(file_path)
    
    # Para cada tipo, ordenar por data de modificação (mais recente primeiro)
    # e manter apenas os N mais recentes
    for file_type, files in files_by_type.items():
        keep_count = log_patterns.get(file_type, keep_recent)
        
        # Ordenar por data de modificação (mais recente primeiro)
        files_sorted = sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)
        
        # Separar: manter vs deletar
        to_keep = files_sorted[:keep_count]
        to_delete = files_sorted[keep_count:]
        
        # Deletar arquivos antigos
        deleted_count = 0
        for file_path in to_delete:
            try:
                file_path.unlink()
                deleted_count += 1
            except Exception as e:
                print(f"Erro ao deletar {file_path}: {e}")
        
        stats["by_type"][file_type] = {
            "deleted": deleted_count,
            "kept": len(to_keep)
        }
        stats["deleted"] += deleted_count
        stats["kept"] += len(to_keep)
    
    return stats


def auto_cleanup_logs(base_dir: Path = None, keep_recent: int = 5):
    """
    Limpeza automática de logs. Chamada após gerar novos logs.
    
    Args:
        base_dir: Diretório base do projeto (se None, tenta descobrir)
        keep_recent: Quantos arquivos manter de cada tipo
    """
    if base_dir is None:
        # Tentar descobrir o diretório base
        base_dir = Path(__file__).resolve().parents[2]
    
    log_dir = base_dir / "logs"
    
    if not log_dir.exists():
        return
    
    # Limpar logs antigos
    stats = cleanup_old_logs(log_dir, keep_recent=keep_recent)
    
    if stats["deleted"] > 0:
        print(f"Limpeza de logs: {stats['deleted']} arquivos deletados, {stats['kept']} mantidos")
        for file_type, counts in stats["by_type"].items():
            if counts["deleted"] > 0:
                print(f"  {file_type}: {counts['deleted']} deletados, {counts['kept']} mantidos")

