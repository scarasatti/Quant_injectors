import json
import os
from datetime import datetime, time
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
from io import BytesIO


async def process_excel_file(
    file_contents: bytes,
    filename: str,
    sequencing_date: datetime,
    default_billing_deadline_time: str,
    next_saturday_is_working: bool,
    machine_states: Optional[list] = None,
    programmed_stops: Optional[list] = None,
    processing_calculation: Optional[Dict] = None,
) -> Dict:
    """Processa um arquivo Excel e cria logs com todas as informações encontradas.

    - Salva um JSON em `logs/` com todos os dados da planilha + cálculos.
    - Salva um TXT legível com tabelas:
      * Informações gerais
      * Machine States
      * Paradas Programadas
      * Tabela de jobs com cycle_bottleneck, production_time, deadline, etc.
    """

    # Converter default_billing_deadline_time de string para time
    try:
        # Tentar formato HH:MM:SS
        time_parts = default_billing_deadline_time.split(":")
        default_time = time(
            int(time_parts[0]),
            int(time_parts[1]),
            int(time_parts[2]) if len(time_parts) > 2 else 0,
        )
    except Exception:
        # Se falhar, usar padrão
        default_time = time(16, 59, 0)

    # Ler o arquivo Excel
    df = pd.read_excel(BytesIO(file_contents), engine="openpyxl")

    # Normalizar nomes das colunas (remover espaços extras)
    df.columns = df.columns.str.strip()

    # Criar log com informações da planilha
    log_data: Dict[str, object] = {
        "timestamp": datetime.now().isoformat(),
        "arquivo": filename,
        "sequencing_date": sequencing_date.isoformat(),
        "default_billing_deadline_time": default_time.isoformat(),
        "next_saturday_is_working": next_saturday_is_working,
        "machine_states": machine_states if machine_states else [],
        "programmed_stops": programmed_stops if programmed_stops else [],
        "processing_calculation": processing_calculation if processing_calculation else None,
        "total_linhas": len(df),
        "colunas_encontradas": list(df.columns),
        "tipos_dados": {col: str(df[col].dtype) for col in df.columns},
        "dados": [],
    }

    # Processar cada linha para o log textual/JSON (valores como string)
    for idx, row in df.iterrows():
        linha_dict: Dict[str, object] = {
            "numero_linha_excel": idx + 2,  # +2 porque idx começa em 0 e pula o header
            "dados": {},
        }

        for col in df.columns:
            valor = row[col]

            # Converter para string para log, tratando NaN
            if pd.isna(valor):
                valor_str = "NaN/Vazio"
                tipo_valor = "NaN"
                raw_val = "NaN"
            else:
                valor_str = str(valor)
                tipo_valor = type(valor).__name__
                raw_val = repr(valor)

            linha_dict["dados"][col] = {
                "valor": valor_str,
                "tipo": tipo_valor,
                "raw": raw_val,
            }

        log_data["dados"].append(linha_dict)

    # Diretório de logs fixo na raiz do projeto
    base_dir = Path(__file__).resolve().parents[2]  # .../Quant_injectors
    log_dir = base_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    # Limpeza automática de logs antigos antes de criar novo
    try:
        from algorithm.injection.log_cleanup import auto_cleanup_logs
        auto_cleanup_logs(base_dir, keep_recent=5)
    except Exception as e:
        print(f"Erro na limpeza de logs: {e}")
    
    # Salvar log em arquivo JSON
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = f"excel_read_{timestamp_str}.json"
    log_path = log_dir / log_filename

    with log_path.open("w", encoding="utf-8") as f:
        json.dump(log_data, f, ensure_ascii=False, indent=2)

    # Criar também um log em texto mais legível
    log_text_filename = f"excel_read_{timestamp_str}.txt"
    log_text_path = log_dir / log_text_filename

    with log_text_path.open("w", encoding="utf-8") as f:
        f.write("LOG DE LEITURA DE PLANILHA EXCEL\n")
        f.write(f"{'='*80}\n\n")
        f.write(f"Timestamp: {log_data['timestamp']}\n")
        f.write(f"Arquivo: {log_data['arquivo']}\n")
        f.write(f"Sequencing Date: {log_data['sequencing_date']}\n")
        f.write(f"Default Billing Deadline Time: {log_data['default_billing_deadline_time']}\n")
        f.write(f"Next Saturday Is Working: {log_data['next_saturday_is_working']}\n")
        if log_data.get("machine_states"):
            f.write(
                f"Machine States Recebidos: {len(log_data['machine_states'])}\n"
            )
        if log_data.get("programmed_stops"):
            f.write(
                f"Paradas Programadas Recebidas: {len(log_data['programmed_stops'])}\n"
            )
        f.write(
            f"Total de linhas (excluindo header): {log_data['total_linhas']}\n\n"
        )

        # Seção de Machine States
        if log_data.get("machine_states"):
            f.write("\n")
            f.write("ESTADO DAS MÁQUINAS (MACHINE STATES):\n")
            f.write(f"{'='*80}\n\n")
            f.write(f"Total de estados recebidos: {len(log_data['machine_states'])}\n\n")

            machine_cols = [
                "production_line_id",
                "machine_id",
                "used",
                "completed",
                "mold_id",
                "product_id",
                "order_number",
                "client_name",
                "remaining_injection_hours",
                "remaining_post_injection_hours",
                "demand",
                "billing_value",
                "billing_deadline_date",
                "billing_deadline_time",
            ]

            machine_larguras: Dict[str, int] = {}
            for col in machine_cols:
                # Largura mínima baseada no nome da coluna
                machine_larguras[col] = max(len(str(col)), 8)
                # Verificar valores para ajustar largura
                for state in log_data["machine_states"]:
                    valor = state.get(col, "N/A")
                    valor_str = str(valor)
                    if len(valor_str) > machine_larguras[col]:
                        machine_larguras[col] = min(len(valor_str), 30)

            f.write("MACHINE STATES RECEBIDOS (formato tabular):\n")
            f.write(f"{'-'*80}\n\n")

            # Cabeçalho
            header = "ID | "
            separator = "----|"
            for col in machine_cols:
                largura = machine_larguras[col]
                header += f" {col[:largura]:<{largura}} |"
                separator += "-" * (largura + 2) + "|"

            f.write(header + "\n")
            f.write(separator + "\n")

            # Dados
            for idx, state in enumerate(log_data['machine_states'], 1):
                linha_str = f"{idx:>3} | "
                for col in machine_cols:
                    largura = machine_larguras[col]
                    valor = state.get(col, 'N/A')
                    valor_str = str(valor) if valor is not None else "N/A"
                    # Truncar se muito longo
                    if len(valor_str) > largura:
                        valor_str = valor_str[: largura - 3] + "..."
                    linha_str += f" {valor_str:<{largura}} |"
                f.write(linha_str + "\n")

            f.write("\n")

        # Seção de Paradas Programadas
        if log_data.get("programmed_stops"):
            f.write("\n")
            f.write("PARADAS PROGRAMADAS (PROGRAMMED STOPS):\n")
            f.write(f"{'='*80}\n\n")
            f.write(
                f"Total de paradas recebidas: {len(log_data['programmed_stops'])}\n\n"
            )

            stop_cols = [
                "reason",
                "machine_id",
                "start_date",
                "start_time",
                "end_date",
                "end_time",
            ]

            stop_larguras: Dict[str, int] = {}
            for col in stop_cols:
                stop_larguras[col] = max(len(str(col)), 10)
                for stop in log_data["programmed_stops"]:
                    valor = stop.get(col, "N/A")
                    valor_str = str(valor) if valor is not None else "N/A"
                    if len(valor_str) > stop_larguras[col]:
                        stop_larguras[col] = min(len(valor_str), 30)

            f.write("PARADAS PROGRAMADAS RECEBIDAS (formato tabular):\n")
            f.write(f"{'-'*80}\n\n")

            # Cabeçalho
            header = "ID | "
            separator = "----|"
            for col in stop_cols:
                largura = stop_larguras[col]
                header += f" {col[:largura]:<{largura}} |"
                separator += "-" * (largura + 2) + "|"

            f.write(header + "\n")
            f.write(separator + "\n")

            # Dados
            for idx, stop in enumerate(log_data['programmed_stops'], 1):
                linha_str = f"{idx:>3} | "
                for col in stop_cols:
                    largura = stop_larguras[col]
                    valor = stop.get(col, 'N/A')
                    valor_str = str(valor) if valor is not None else "N/A"
                    if len(valor_str) > largura:
                        valor_str = valor_str[: largura - 3] + "..."
                    linha_str += f" {valor_str:<{largura}} |"
                f.write(linha_str + "\n")

            f.write("\n")

        # Lista de colunas e tipos
        f.write(f"COLUNAS ENCONTRADAS ({len(log_data['colunas_encontradas'])}):\n")
        f.write(f"{'-'*80}\n")
        for i, col in enumerate(log_data['colunas_encontradas'], 1):
            tipo = log_data['tipos_dados'][col]
            f.write(f"{i}. '{col}' (tipo: {tipo})\n")
        f.write("\n")

        # Tabela de dados da planilha
        if log_data["dados"]:
            colunas: List[str] = log_data["colunas_encontradas"]

            larguras: Dict[str, int] = {}
            for col in colunas:
                larguras[col] = max(len(str(col)), 10)
                for linha in log_data["dados"]:
                    if col in linha["dados"]:
                        valor_len = len(str(linha["dados"][col]["valor"]))
                        if valor_len > larguras[col]:
                            larguras[col] = min(valor_len, 50)

            f.write("DADOS DAS LINHAS (formato tabular):\n")
            f.write(f"{'='*80}\n\n")

            header = ""
            separator = ""
            for col in colunas:
                largura = larguras[col]
                header += f" {col[:largura]:<{largura}} |"
                separator += "-" * (largura + 2) + "|"

            f.write(header + "\n")
            f.write(separator + "\n")

            for linha in log_data["dados"]:
                linha_str = ""
                for col in colunas:
                    largura = larguras[col]
                    if col in linha["dados"]:
                        valor = str(linha["dados"][col]["valor"])
                        if len(valor) > largura:
                            valor = valor[: largura - 3] + "..."
                        linha_str += f" {valor:<{largura}} |"
                    else:
                        linha_str += f" {'N/A':<{largura}} |"
                f.write(linha_str + "\n")

            f.write("\n")

        # Seção de Cálculo de Processing Time (por último, depois da planilha)
        if log_data.get("processing_calculation"):
            calc: Dict = log_data["processing_calculation"]
            f.write("\n")
            f.write("CÁLCULO DE PROCESSING TIME:\n")
            f.write(f"{'='*80}\n\n")
            f.write(f"Total de jobs processados: {calc.get('total_jobs', 0)}\n")
            f.write(f"Total de linhas de produção: {calc.get('total_lines', 0)}\n")

            if calc.get("errors"):
                f.write(f"Erros encontrados: {len(calc['errors'])}\n")
                for error in calc["errors"]:
                    f.write(f"  - {error}\n")
            f.write("\n")

            # Mostrar jobs por linha
            jobs_by_line: Dict = calc.get("jobs_by_line", {})
            for line_id, line_data in jobs_by_line.items():
                f.write(
                    f"LINHA DE PRODUÇÃO {line_id} ({line_data.get('production_line_name', 'N/A')}):\n"
                )
                f.write(f"{'-'*80}\n")
                f.write(f"Total de jobs: {len(line_data.get('jobs', []))}\n")
                f.write(
                    f"Máquinas: {', '.join([m.get('machine_name', 'N/A') for m in line_data.get('machines', [])])}\n\n"
                )

                # Tabela de jobs com cycle_bottleneck e tempos
                if line_data.get("jobs"):
                    f.write("JOBS E CÁLCULOS DE CYCLE_BOTTLENECK:\n")
                    f.write(f"{'-'*80}\n\n")

                    # Definir colunas (ordem já ajustada acima)
                    job_cols = [
                        "product_name",
                        "mold_name",
                        "demand",
                        "unit_value",  # NOVO: Valor unitário para cálculo de faturamento
                        "scrap_percent",
                        "closed_cavity_risk_percent",
                        "scrap_factor",
                        "demand_with_scrap",
                        "machine_name",
                        "cycle_time",
                        "availability",
                        "available_factor",
                        "cycle_bottleneck",
                        "production_time",
                        "total_post_injection_time",
                        "deadline_hours",
                        "deadline_in_injection",
                    ]

                    # Calcular larguras
                    job_larguras: Dict[str, int] = {}
                    for col in job_cols:
                        job_larguras[col] = max(len(str(col)), 10)
                        for job in line_data["jobs"]:
                            if col == "product_name":
                                v = job.get(col)
                                if v is not None:
                                    valor_len = len(str(v))
                                    if valor_len > job_larguras[col]:
                                        job_larguras[col] = min(valor_len, 30)
                            elif col == "mold_name":
                                v = job.get(col)
                                if v is not None:
                                    valor_len = len(str(v))
                                    if valor_len > job_larguras[col]:
                                        job_larguras[col] = min(valor_len, 30)
                            elif col == "machine_name":
                                # Para máquinas, pegar o maior nome
                                for machine in job.get("processing_time_by_machine", []):
                                    v = machine.get("machine_name")
                                    valor_len = len(str(v)) if v is not None else 3
                                    if valor_len > job_larguras[col]:
                                        job_larguras[col] = min(valor_len, 25)
                            elif col in ["demand", "demand_with_scrap"]:
                                v = job.get(col)
                                if v is not None:
                                    try:
                                        valor_len = len(f"{int(v)}")
                                        if valor_len > job_larguras[col]:
                                            job_larguras[col] = min(valor_len, 15)
                                    except (ValueError, TypeError):
                                        pass
                            elif col == "unit_value":
                                v = job.get(col)
                                if v is not None:
                                    try:
                                        valor_len = len(f"{float(v):.2f}")
                                        if valor_len > job_larguras[col]:
                                            job_larguras[col] = min(valor_len, 12)
                                    except (ValueError, TypeError):
                                        pass
                            elif col in ["deadline_hours", "total_post_injection_time", "deadline_in_injection"]:
                                v = job.get(col)
                                if v is not None:
                                    try:
                                        valor_len = len(f"{float(v):.2f}")
                                        if valor_len > job_larguras[col]:
                                            job_larguras[col] = min(valor_len, 15)
                                    except (ValueError, TypeError):
                                        pass
                            elif col in ["scrap_percent", "closed_cavity_risk_percent"]:
                                v = job.get(col)
                                if v is not None:
                                    try:
                                        valor_len = len(f"{float(v):.2f}%")
                                        if valor_len > job_larguras[col]:
                                            job_larguras[col] = min(valor_len, 12)
                                    except (ValueError, TypeError):
                                        pass
                            elif col == "scrap_factor":
                                v = job.get(col)
                                if v is not None:
                                    try:
                                        valor_len = len(f"{float(v):.2f}")
                                        if valor_len > job_larguras[col]:
                                            job_larguras[col] = min(valor_len, 12)
                                    except (ValueError, TypeError):
                                        pass
                            elif col == "production_time":
                                for machine in job.get("processing_time_by_machine", []):
                                    v = machine.get("production_time")
                                    if v is not None:
                                        try:
                                            valor_len = len(f"{float(v):.2f}")
                                            if valor_len > job_larguras[col]:
                                                job_larguras[col] = min(valor_len, 15)
                                        except (ValueError, TypeError):
                                            pass
                            elif col in job:
                                v = job[col]
                                if v is not None:
                                    valor_len = len(str(v))
                                    if valor_len > job_larguras[col]:
                                        job_larguras[col] = min(valor_len, 20)

                    # Cabeçalho
                    header = ""
                    separator = ""
                    for col in job_cols:
                        largura = job_larguras[col]
                        header += f" {col[:largura]:<{largura}} |"
                        separator += "-" * (largura + 2) + "|"

                    f.write(header + "\n")
                    f.write(separator + "\n")

                    # Dados - uma linha por máquina de cada job
                    for job in line_data["jobs"]:
                        for machine in job.get("processing_time_by_machine", []):
                            linha_str = ""
                            for col in job_cols:
                                largura = job_larguras[col]
                                if col == "product_name":
                                    v = job.get(col)
                                    valor = "N/A" if v is None else str(v)
                                elif col == "mold_name":
                                    v = job.get(col)
                                    valor = "N/A" if v is None else str(v)
                                elif col == "demand":
                                    v = job.get(col)
                                    if v is None:
                                        valor = "N/A"
                                    else:
                                        try:
                                            valor = f"{int(v)}"
                                        except (ValueError, TypeError):
                                            valor = "N/A"
                                elif col == "unit_value":
                                    v = job.get(col)
                                    if v is None or v == 0.0:
                                        valor = "0.00"
                                    else:
                                        try:
                                            valor = f"{float(v):.2f}"
                                        except (ValueError, TypeError):
                                            valor = "0.00"
                                elif col == "scrap_percent":
                                    v = job.get(col)
                                    if v is None:
                                        valor = "N/A"
                                    else:
                                        try:
                                            valor = f"{float(v):.2f}%"
                                        except (ValueError, TypeError):
                                            valor = "N/A"
                                elif col == "closed_cavity_risk_percent":
                                    v = job.get(col)
                                    if v is None:
                                        valor = "N/A"
                                    else:
                                        try:
                                            valor = f"{float(v):.2f}%"
                                        except (ValueError, TypeError):
                                            valor = "N/A"
                                elif col == "scrap_factor":
                                    v = job.get(col)
                                    if v is None:
                                        valor = "N/A"
                                    else:
                                        try:
                                            valor = f"{float(v):.2f}"
                                        except (ValueError, TypeError):
                                            valor = "N/A"
                                elif col == "demand_with_scrap":
                                    v = job.get(col)
                                    if v is None:
                                        valor = "N/A"
                                    else:
                                        try:
                                            valor = f"{int(v)}"
                                        except (ValueError, TypeError):
                                            valor = "N/A"
                                elif col == "deadline_hours":
                                    v = job.get(col)
                                    if v is None:
                                        valor = "N/A"
                                    else:
                                        try:
                                            valor = f"{float(v):.2f}"
                                        except (ValueError, TypeError):
                                            valor = "N/A"
                                elif col == "total_post_injection_time":
                                    v = job.get(col)
                                    if v is None:
                                        valor = "N/A"
                                    else:
                                        try:
                                            valor = f"{float(v):.2f}"
                                        except (ValueError, TypeError):
                                            valor = "N/A"
                                elif col == "deadline_in_injection":
                                    v = job.get(col)
                                    if v is None:
                                        valor = "N/A"
                                    else:
                                        try:
                                            valor = f"{float(v):.2f}"
                                        except (ValueError, TypeError):
                                            valor = "N/A"
                                elif col == "machine_name":
                                    v = machine.get("machine_name")
                                    valor = "N/A" if v is None else str(v)
                                elif col == "cycle_time":
                                    v = machine.get("cycle_time")
                                    valor = "N/A" if v is None else str(v)
                                elif col == "availability":
                                    v = machine.get("availability")
                                    valor = "N/A" if v is None else str(v)
                                elif col == "available_factor":
                                    v = machine.get("available_factor")
                                    if v is None:
                                        valor = "N/A"
                                    else:
                                        try:
                                            valor = f"{float(v):.2f}"
                                        except (ValueError, TypeError):
                                            valor = "N/A"
                                elif col == "cycle_bottleneck":
                                    v = machine.get("cycle_bottleneck")
                                    if v is None:
                                        valor = "N/A"
                                    else:
                                        try:
                                            valor = f"{float(v):.2f}"
                                        except (ValueError, TypeError):
                                            valor = "N/A"
                                elif col == "production_time":
                                    v = machine.get("production_time")
                                    if v is None:
                                        valor = "N/A"
                                    else:
                                        try:
                                            valor = f"{float(v):.2f}"
                                        except (ValueError, TypeError):
                                            valor = "N/A"
                                else:
                                    valor = "N/A"

                                if len(valor) > largura:
                                    valor = valor[: largura - 3] + "..."
                                linha_str += f" {valor:<{largura}} |"
                            f.write(linha_str + "\n")
                    f.write("\n")

            f.write("\n")

    return {
        "mensagem": "Planilha processada com sucesso",
        "arquivo": filename,
        "sequencing_date": log_data["sequencing_date"],
        "default_billing_deadline_time": log_data["default_billing_deadline_time"],
        "next_saturday_is_working": log_data["next_saturday_is_working"],
        "total_linhas": log_data["total_linhas"],
        "colunas": log_data["colunas_encontradas"],
        "log_json": log_filename,
        "log_texto": log_text_filename,
        "log_path": str(log_path),
    }







