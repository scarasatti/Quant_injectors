from typing import List, Dict, Optional
from datetime import datetime, date, time

import pandas as pd
from sqlalchemy.orm import Session, joinedload

from app.models.composition_line import CompositionLine
from app.models.composition_line_machine import CompositionLineMachine
from app.models.machine import Machine
from app.models.production_line import ProductionLine
from app.models.production_time import ProductionTime
from app.models.regular_shift import RegularShift
from app.models.holiday import Holiday
from algorithm.injection.due_date_calculator import calculate_due_date, calculate_working_hours_between


def calculate_processing_time(
    excel_rows: List[Dict],
    sequencing_date: datetime,
    next_saturday_is_working: bool,
    db: Session,
    machine_states: Optional[List[Dict]] = None,
    programmed_stops: Optional[List[Dict]] = None,
) -> Dict:
    """Calcula tempos de processamento e prazos para cada linha do Excel.

    - Cada linha da planilha vira um "job" associado a uma `CompositionLine`.
    - Busca `Mold`, `Product`, `CompositionLine`, `ProductionTime` e monta:
        * demand_with_scrap
        * total_post_injection_time
        * cycle_bottleneck / production_time por máquina
        * deadline_hours (horas úteis até a data de entrega)
        * deadline_in_injection = deadline_hours - total_post_injection_time
    """

    jobs_by_line: Dict[int, Dict] = {}
    errors: List[str] = []

    def get_column_value(row: Dict, possible_names: List[str]) -> Optional[str]:
        """Busca um valor em várias possíveis colunas (com fallback case-insensível)."""
        for name in possible_names:
            if name in row:
                v = row[name]
                if pd.notna(v) and str(v).strip() != "":
                    return str(v).strip()

        lower = {k.lower().strip(): k for k in row.keys()}
        for name in possible_names:
            k = lower.get(name.lower().strip())
            if k is not None:
                v = row[k]
                if pd.notna(v) and str(v).strip():
                    return str(v).strip()
        return None

    def get_promised_datetime(row: Dict) -> Optional[datetime]:
        """Constrói o datetime de entrega a partir das colunas da planilha."""
        raw_date = row.get("Data Limite de Faturamento") or row.get("Data Prometida")
        if raw_date is None or (isinstance(raw_date, float) and pd.isna(raw_date)):
            return None

        if isinstance(raw_date, str):
            raw_date = raw_date.strip()
            if not raw_date:
                return None
            promised_date = datetime.strptime(raw_date, "%d/%m/%Y").date()
        elif isinstance(raw_date, pd.Timestamp):
            promised_date = raw_date.to_pydatetime().date()
        elif isinstance(raw_date, datetime):
            promised_date = raw_date.date()
        elif isinstance(raw_date, date):
            promised_date = raw_date
        else:
            return None

        raw_time = (
            row.get("Horário Limite de Faturamento")
            or row.get("Horario Limite de Faturamento")
            or row.get("Horário Prometido")
            or row.get("Horario Prometido")
        )
        if raw_time is None or (isinstance(raw_time, float) and pd.isna(raw_time)):
            return None

        if isinstance(raw_time, str):
            raw_time = raw_time.strip()
            if not raw_time:
                return None
            # Aceitar HH:MM ou HH:MM:SS (planilha pode vir 7:00, 23:00, etc.)
            for fmt in ("%H:%M:%S", "%H:%M"):
                try:
                    promised_time = datetime.strptime(raw_time, fmt).time()
                    break
                except ValueError:
                    continue
            else:
                return None
        elif isinstance(raw_time, pd.Timestamp):
            promised_time = raw_time.to_pydatetime().time()
        elif isinstance(raw_time, datetime):
            promised_time = raw_time.time()
        elif isinstance(raw_time, (int, float)):
            s = f"{int(raw_time):06d}"
            promised_time = time(int(s[0:2]), int(s[2:4]), int(s[4:6]))
        elif isinstance(raw_time, time):
            promised_time = raw_time
        else:
            return None

        return datetime.combine(promised_date, promised_time)

    # ------------------------------
    # 1) Jobs normais vindos da planilha
    # ------------------------------
    for idx, row in enumerate(excel_rows, start=2):
        try:
            # --- Identificação do molde e produto ---
            mold_name = get_column_value(
                row,
                [
                    "Código do Molde",
                    "Codigo do Molde",
                    "Molde",
                    "molde",
                    "Nome do Molde",
                    "Mold",
                    "mold",
                ],
            )
            product_name = get_column_value(
                row,
                [
                    "Produto",
                    "produto",
                    "Product",
                    "product",
                    "Nome do Produto",
                ],
            )

            if not mold_name or not product_name:
                errors.append(
                    f"Linha {idx}: Faltam informações obrigatórias. Molde='{mold_name}', Produto='{product_name}'"
                )
                continue

            from app.models.mold import Mold
            from app.models.product import Product

            product = db.query(Product).filter(Product.name == product_name).first()
            if not product:
                product = (
                    db.query(Product)
                    .filter(Product.name.ilike(f"%{product_name}%"))
                    .first()
                )
            if not product:
                errors.append(f"Linha {idx}: Produto não encontrado: '{product_name}'")
                continue

            mold = db.query(Mold).filter(Mold.name == mold_name).first()
            if not mold:
                mold = db.query(Mold).filter(Mold.name.ilike(f"%{mold_name}%")).first()
            if not mold:
                errors.append(f"Linha {idx}: Molde não encontrado: '{mold_name}'")
                continue

            # --- CompositionLine (usando molde + produto) ---
            q = db.query(CompositionLine).options(
                joinedload(CompositionLine.mold),
                joinedload(CompositionLine.product),
                joinedload(CompositionLine.production_line),
                joinedload(CompositionLine.machines).joinedload(CompositionLineMachine.machine),
            ).filter(
                CompositionLine.mold_id == mold.id,
                CompositionLine.product_id == product.id,
            )

            comp = q.first()

            if not comp:
                errors.append(
                    f"Linha {idx}: CompositionLine não encontrada para molde '{mold_name}', produto '{product_name}'"
                )
                continue

            pl_id = comp.production_line_id
            pl_name = comp.production_line.name if comp.production_line else f"Linha {pl_id}"

            # --- Demanda e scrap ---
            raw_demand = get_column_value(
                row,
                ["Demanda do Pedido", "Demanda", "demanda", "Demand", "demand"],
            )
            if not raw_demand:
                errors.append(f"Linha {idx}: Demanda não encontrada na planilha")
                continue

            try:
                demand = float(raw_demand)
            except (ValueError, TypeError):
                errors.append(f"Linha {idx}: Demanda inválida: '{raw_demand}'")
                continue

            # --- Valor Unitário (para cálculo de faturamento) ---
            # Tentar múltiplas variações de nomes de coluna (case-insensitive)
            raw_unit_value = get_column_value(
                row,
                [
                    "Valor Unitário", "Valor Unitario", "valor unitário", "valor unitario",
                    "Valor Unit", "valor unit", "Unit Value", "unit value",
                    "Valor", "valor", "Value", "value", 
                    "Price", "price", "Preço", "preço", "Preco", "preco",
                    "Valor Unitário (R$)", "Valor Unitario (R$)", 
                    "Preço Unitário", "Preco Unitario", "preço unitário", "preco unitario",
                    "Unit Price", "unit price", "Preço Unit", "preco unit"
                ],
            )
            unit_value = 0.0
            if raw_unit_value:
                try:
                    # Tentar converter diretamente
                    unit_value = float(raw_unit_value)
                except (ValueError, TypeError):
                    # Se falhar, tentar tratar formatos comuns (R$ 20,00 ou 20.000,00)
                    try:
                        # Remover símbolos de moeda e espaços
                        value_str = str(raw_unit_value).strip()
                        value_str = value_str.replace("R$", "").replace("$", "").replace("€", "").replace("£", "").strip()
                        # Substituir vírgula por ponto (formato brasileiro: 20,00 -> 20.00)
                        # Mas primeiro verificar se há ponto como separador de milhar
                        if value_str.count(".") > 0 and value_str.count(",") > 0:
                            # Formato: 20.000,50 -> 20000.50
                            value_str = value_str.replace(".", "").replace(",", ".")
                        elif value_str.count(",") > 0:
                            # Formato: 20,50 -> 20.50
                            value_str = value_str.replace(",", ".")
                        unit_value = float(value_str)
                    except (ValueError, TypeError):
                        # Se ainda falhar, usar 0.0 (não é erro crítico)
                        unit_value = 0.0
            
            # Log para debug
            if unit_value == 0.0:
                print(f"⚠️ Linha {idx}: Valor unitário não encontrado ou inválido. Colunas disponíveis: {list(row.keys())}")
            else:
                print(f"✅ Linha {idx}: Valor unitário lido = {unit_value} (raw: {raw_unit_value})")

            scrap_pct = float(mold.scrap) if mold.scrap is not None else 0.0
            risk_pct = float(mold.closed_cavity_risk) if mold.closed_cavity_risk is not None else 0.0
            scrap_factor = 1 + (scrap_pct / 100.0) + (risk_pct / 100.0)
            demand_with_scrap = demand * scrap_factor

            # --- Pós-injeção ---
            post_cycle = comp.post_injection_cycle_time if comp.post_injection_cycle_time is not None else 0  # em segundos
            total_post_injection_time = (demand_with_scrap * post_cycle) / 3600.0

            # --- Deadline (horas úteis até a data de entrega) ---
            promised = get_promised_datetime(row)
            if not promised:
                errors.append(
                    f"Linha {idx}: Data/hora limite de faturamento inválida ou ausente (Data Limite / Horário Limite)"
                )
                continue

            deadline_hours = calculate_due_date(
                promised_date=promised,
                sequencing_date=sequencing_date,
                db=db,
                next_saturday_is_working=next_saturday_is_working,
            )

            # --- Deadline dentro da injeção ---
            deadline_in_injection = deadline_hours - total_post_injection_time
            # Arredondar para 1 casa decimal
            deadline_in_injection = round(deadline_in_injection, 1)

            # Inicializa estrutura da linha de produção
            if pl_id not in jobs_by_line:
                jobs_by_line[pl_id] = {
                    "production_line_id": pl_id,
                    "production_line_name": pl_name,
                    "jobs": [],
                    "machines": [],
                }

            # --- Máquinas e tempos de gargalo ---
            machines_data: List[Dict] = []
            for clm in comp.machines:
                m: Machine = clm.machine
                pt = (
                    db.query(ProductionTime)
                    .filter(
                        ProductionTime.machine_id == m.id,
                        ProductionTime.product_id == comp.product_id,
                        ProductionTime.mold_id == mold.id,
                    )
                    .first()
                )
                if not pt:
                    errors.append(
                        f"Linha {idx}: ProductionTime não encontrado para máquina {m.id}, produto {comp.product_id}, molde {mold.id}"
                    )
                    continue

                cycle_time = pt.tempo_ciclo if pt.tempo_ciclo is not None else 0  # segundos por cavada
                avail = float(m.availability) if m.availability is not None else 100.0  # %
                available_factor = (100.0 - avail) / 100.0 + 1.0

                cycle_bottleneck = cycle_time * available_factor  # segundos por peça efetivo

                open_cavities = mold.open_cavities if mold.open_cavities is not None else 1
                production_time_hours = (demand_with_scrap * cycle_bottleneck / open_cavities) / 3600.0
                
                # Arredondar para 1 casa decimal
                production_time_hours = round(production_time_hours, 1)

                machines_data.append(
                    {
                        "machine_id": m.id,
                        "machine_name": m.name,
                        "availability": avail,
                        "available_factor": available_factor,
                        "cycle_time": cycle_time,
                        "cycle_bottleneck": cycle_bottleneck,
                        "production_time": production_time_hours,
                    }
                )

            # Serializar linha original para debug
            row_serializable: Dict[str, Optional[str]] = {}
            for k, v in row.items():
                if pd.isna(v):
                    row_serializable[k] = None
                elif isinstance(v, pd.Timestamp):
                    row_serializable[k] = v.isoformat()
                else:
                    row_serializable[k] = str(v)

            job_data = {
                "composition_line_id": comp.id,
                "mold_id": mold.id,
                "mold_name": mold.name,
                "product_id": comp.product_id,
                "product_name": comp.product.name,
                "demand": demand,
                "unit_value": unit_value,  # Valor unitário da planilha
                "scrap_percent": scrap_pct,
                "closed_cavity_risk_percent": risk_pct,
                "scrap_factor": scrap_factor,
                "demand_with_scrap": demand_with_scrap,
                "post_injection_cycle_time": post_cycle,
                "total_post_injection_time": total_post_injection_time,
                "deadline_hours": deadline_hours,
                "deadline_in_injection": deadline_in_injection,
                "processing_time_by_machine": machines_data,
                "row_data": row_serializable,
                "promised_date": promised.isoformat() if promised else None,  # JSON-serializable (ISO)
            }

            jobs_by_line[pl_id]["jobs"].append(job_data)

            # Atualizar lista de máquinas únicas da linha
            for md in machines_data:
                if md["machine_id"] not in [m["machine_id"] for m in jobs_by_line[pl_id]["machines"]]:
                    jobs_by_line[pl_id]["machines"].append(
                        {
                            "machine_id": md["machine_id"],
                            "machine_name": md["machine_name"],
                            "availability": md["availability"],
                        }
                    )

        except Exception as exc:
            errors.append(f"Linha {idx}: Erro ao processar - {exc}")
            continue

    # ------------------------------
    # 2) Jobs falsos vindos do state_machine (machine_states)
    # ------------------------------
    if machine_states:
        for idx, state in enumerate(machine_states, start=1):
            try:
                pl_id = state.get("production_line_id")
                machine_id = state.get("machine_id")
                used = bool(state.get("used", False))
                mold_name = state.get("mold_name")
                product_name = state.get("product_name")
                client_name = state.get("client_name")  # PEGAR DO JSON

                if pl_id is None or machine_id is None:
                    errors.append(
                        f"StateMachine {idx}: production_line_id ou machine_id ausente no JSON: {state}"
                    )
                    continue
                
                # Pular jobs onde a máquina não está sendo usada (used == False)
                # Esses jobs não devem ser criados
                if not used:
                    continue

                # Verificar se o job foi concluído
                completed = bool(state.get("completed", False))

                # Buscar mold_id e product_id a partir dos nomes fornecidos
                mold_id = None
                product_id = None
                
                if mold_name:
                    from app.models.mold import Mold
                    mold = db.query(Mold).filter(Mold.name == mold_name).first()
                    if not mold:
                        mold = db.query(Mold).filter(Mold.name.ilike(f"%{mold_name}%")).first()
                    if mold:
                        mold_id = mold.id
                    else:
                        errors.append(f"StateMachine {idx}: Molde não encontrado: '{mold_name}'")
                
                if product_name:
                    from app.models.product import Product
                    product = db.query(Product).filter(Product.name == product_name).first()
                    if not product:
                        product = (
                            db.query(Product)
                            .filter(Product.name.ilike(f"%{product_name}%"))
                            .first()
                        )
                    if product:
                        product_id = product.id
                    else:
                        errors.append(f"StateMachine {idx}: Produto não encontrado: '{product_name}'")

                # Calcular production_time a partir do valor informado no JSON
                # Regras:
                # - Se máquina não for utilizada (used == False), tempo = 99999
                # - Se job foi concluído (completed == True), tempo = 0 (apenas gera setup, não ocupa máquina)
                # - Se job em andamento (completed == False), tempo = remaining_injection_hours
                if not used:
                    production_time_hours = 99999.0
                elif completed:
                    # Job concluído: tempo de produção = 0 (máquina livre)
                    # Mas o job será criado para gerar setup baseado no produto atual da máquina
                    production_time_hours = 0.0
                else:
                    raw_time = state.get("remaining_injection_hours")
                    try:
                        # Valor de entrada considerado em minutos -> converter para horas
                        production_time_hours = float(raw_time) / 60.0
                        # Arredondar para 1 casa decimal
                        production_time_hours = round(production_time_hours, 1)
                    except (TypeError, ValueError):
                        production_time_hours = None

                # Para jobs falsos do state_machine:
                # - deadline_hours: não calculamos (sempre None)
                # - deadline_in_injection: 
                #   * Se completed=True: 0 (job não ocupa tempo, apenas gera setup)
                #   * Se completed=False: igual a production_time (job em andamento)
                #   * Se used=False: None (não deveria chegar aqui devido ao continue acima)
                deadline_hours = None
                total_post_injection_time = None
                
                if used and production_time_hours is not None:
                    if completed:
                        # Job concluído: deadline = 0 (não precisa de tempo de execução)
                        deadline_in_injection = 0.0
                    else:
                        # Job em andamento: deadline = tempo restante
                        deadline_in_injection = production_time_hours
                else:
                    deadline_in_injection = None

                # Inicializar estrutura da linha se ainda não existir
                if pl_id not in jobs_by_line:
                    production_line = db.query(ProductionLine).filter(ProductionLine.id == pl_id).first()
                    pl_name = production_line.name if production_line else f"Linha {pl_id}"
                    jobs_by_line[pl_id] = {
                        "production_line_id": pl_id,
                        "production_line_name": pl_name,
                        "jobs": [],
                        "machines": [],
                    }

                # Buscar todas as máquinas da linha através de CompositionLine
                all_comp_lines_in_pl = (
                    db.query(CompositionLine)
                    .options(
                        joinedload(CompositionLine.machines).joinedload(CompositionLineMachine.machine)
                    )
                    .filter(CompositionLine.production_line_id == pl_id)
                    .all()
                )

                # Coletar todas as máquinas únicas da linha
                machines_in_line = {}
                for comp_line in all_comp_lines_in_pl:
                    for clm in comp_line.machines:
                        m = clm.machine
                        if m.id not in machines_in_line:
                            machines_in_line[m.id] = m

                # Criar machines_data com TODAS as máquinas da linha
                machines_data: List[Dict] = []
                for m_id, m in machines_in_line.items():
                    # Se for a máquina do state_machine, usa o production_time calculado
                    # (que já considera completed: 0 se completed=True, remaining_time se completed=False)
                    # Se for outra máquina, usa 99999
                    if m_id == machine_id:
                        machine_production_time = production_time_hours
                    else:
                        machine_production_time = 99999.0
                    
                    machines_data.append({
                        "machine_id": m.id,
                        "machine_name": m.name,
                        "availability": None,
                        "available_factor": None,
                        "cycle_time": None,
                        "cycle_bottleneck": None,
                        "production_time": machine_production_time,
                    })

                # row_data com tudo que veio do JSON, para debug
                row_serializable: Dict[str, Optional[str]] = {}
                for k, v in state.items():
                    if isinstance(v, (datetime, pd.Timestamp)):
                        row_serializable[k] = v.isoformat()
                    else:
                        row_serializable[k] = None if v is None else str(v)

                fake_job = {
                    "composition_line_id": None,
                    "mold_id": mold_id,
                    "mold_name": mold_name,
                    "product_id": product_id,
                    "product_name": product_name,
                    "client_name": client_name,
                    "order_number": state.get("order_number"),
                    "demand": state.get("demand"),
                    "billing_value": state.get("billing_value"),
                    "scrap_percent": None,
                    "closed_cavity_risk_percent": None,
                    "scrap_factor": None,
                    "demand_with_scrap": None,
                    "post_injection_cycle_time": None,
                    "total_post_injection_time": total_post_injection_time,
                    # Preservar data/hora prometida exatamente como veio no JSON da state_machine
                    "billing_deadline_date": state.get("billing_deadline_date"),
                    "billing_deadline_time": state.get("billing_deadline_time"),
                    "deadline_hours": deadline_hours,
                    "deadline_in_injection": deadline_in_injection,
                    "processing_time_by_machine": machines_data,
                    "row_data": row_serializable,
                    "completed": completed,
                    "remaining_post_injection_hours": state.get("remaining_post_injection_hours"),  # Preservar para cálculo do final_completion_time_hours
                }

                jobs_by_line[pl_id]["jobs"].append(fake_job)

                # Atualizar lista de máquinas únicas da linha
                if machine_id not in [m["machine_id"] for m in jobs_by_line[pl_id]["machines"]]:
                    jobs_by_line[pl_id]["machines"].append(
                        {
                            "machine_id": machine_id,
                            "machine_name": machine_name,
                            "availability": None,
                        }
                    )

            except Exception as exc:
                errors.append(f"StateMachine {idx}: Erro ao processar - {exc}")
                continue

    # ------------------------------
    # 3) Jobs falsos vindos de paradas programadas (programmed_stops)
    # ------------------------------
    if programmed_stops:
        for idx, stop in enumerate(programmed_stops, start=1):
            try:
                machine_id = stop.get("machine_id")
                reason = stop.get("reason", "Parada Programada")
                start_date_str = stop.get("start_date")
                start_time_str = stop.get("start_time")
                end_date_str = stop.get("end_date")
                end_time_str = stop.get("end_time")

                if machine_id is None:
                    errors.append(f"ProgrammedStop {idx}: machine_id ausente no JSON: {stop}")
                    continue

                if not start_date_str or not start_time_str or not end_date_str or not end_time_str:
                    errors.append(f"ProgrammedStop {idx}: Datas/horários ausentes no JSON: {stop}")
                    continue

                # Parsear datas e horários
                try:
                    # Parsear start_date
                    if isinstance(start_date_str, str):
                        if "/" in start_date_str:
                            start_date = datetime.strptime(start_date_str, "%d/%m/%Y").date()
                        elif "-" in start_date_str:
                            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
                        else:
                            start_date = None
                    elif isinstance(start_date_str, (date, datetime)):
                        start_date = start_date_str.date() if isinstance(start_date_str, datetime) else start_date_str
                    else:
                        start_date = None

                    # Parsear start_time
                    if isinstance(start_time_str, str):
                        if len(start_time_str.split(":")) == 3:
                            start_time = datetime.strptime(start_time_str, "%H:%M:%S").time()
                        elif len(start_time_str.split(":")) == 2:
                            start_time = datetime.strptime(start_time_str, "%H:%M").time()
                        else:
                            start_time = None
                    elif isinstance(start_time_str, time):
                        start_time = start_time_str
                    else:
                        start_time = None

                    # Parsear end_date
                    if isinstance(end_date_str, str):
                        if "/" in end_date_str:
                            end_date = datetime.strptime(end_date_str, "%d/%m/%Y").date()
                        elif "-" in end_date_str:
                            end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
                        else:
                            end_date = None
                    elif isinstance(end_date_str, (date, datetime)):
                        end_date = end_date_str.date() if isinstance(end_date_str, datetime) else end_date_str
                    else:
                        end_date = None

                    # Parsear end_time
                    if isinstance(end_time_str, str):
                        if len(end_time_str.split(":")) == 3:
                            end_time = datetime.strptime(end_time_str, "%H:%M:%S").time()
                        elif len(end_time_str.split(":")) == 2:
                            end_time = datetime.strptime(end_time_str, "%H:%M").time()
                        else:
                            end_time = None
                    elif isinstance(end_time_str, time):
                        end_time = end_time_str
                    else:
                        end_time = None

                    if not start_date or not start_time or not end_date or not end_time:
                        errors.append(f"ProgrammedStop {idx}: Erro ao parsear datas/horários")
                        continue

                    start_datetime = datetime.combine(start_date, start_time)
                    end_datetime = datetime.combine(end_date, end_time)

                    # Calcular production_time = diferença em horas entre start e end
                    time_diff = end_datetime - start_datetime
                    production_time_hours = time_diff.total_seconds() / 3600.0
                    # Arredondar para 1 casa decimal
                    production_time_hours = round(production_time_hours, 1)

                except Exception as exc:
                    errors.append(f"ProgrammedStop {idx}: Erro ao parsear datas/horários - {exc}")
                    continue

                # Buscar a máquina e descobrir a linha de produção através de CompositionLine
                # Primeiro, encontrar uma CompositionLine que tenha essa máquina
                comp_line_with_machine = (
                    db.query(CompositionLine)
                    .join(CompositionLineMachine)
                    .filter(CompositionLineMachine.machine_id == machine_id)
                    .first()
                )

                if not comp_line_with_machine:
                    errors.append(f"ProgrammedStop {idx}: Máquina {machine_id} não está associada a nenhuma CompositionLine")
                    continue

                pl_id = comp_line_with_machine.production_line_id
                production_line = db.query(ProductionLine).filter(ProductionLine.id == pl_id).first()
                pl_name = production_line.name if production_line else f"Linha {pl_id}"

                # Buscar todas as CompositionLines da mesma linha de produção
                all_comp_lines_in_pl = (
                    db.query(CompositionLine)
                    .options(
                        joinedload(CompositionLine.machines).joinedload(CompositionLineMachine.machine)
                    )
                    .filter(CompositionLine.production_line_id == pl_id)
                    .all()
                )

                # Coletar todas as máquinas únicas da linha através das CompositionLines
                machines_in_line = {}
                for comp_line in all_comp_lines_in_pl:
                    for clm in comp_line.machines:
                        m = clm.machine
                        if m.id not in machines_in_line:
                            machines_in_line[m.id] = m

                # Calcular deadline_in_injection = horas úteis entre sequencing_date e end_datetime
                deadline_in_injection = None
                try:
                    regular_shifts = db.query(RegularShift).all()
                    holidays = [h.date for h in db.query(Holiday).all()]
                    
                    deadline_in_injection = calculate_working_hours_between(
                        start_datetime=sequencing_date,
                        end_datetime=end_datetime,
                        regular_shifts=regular_shifts,
                        holidays=holidays,
                        reference_date=sequencing_date.date(),
                        next_saturday_is_working=next_saturday_is_working
                    )
                    # Arredondar para 1 casa decimal
                    if deadline_in_injection is not None:
                        deadline_in_injection = round(deadline_in_injection, 1)
                except Exception as exc:
                    errors.append(f"ProgrammedStop {idx}: Erro ao calcular deadline_in_injection - {exc}")

                # Inicializar estrutura da linha se ainda não existir
                if pl_id not in jobs_by_line:
                    jobs_by_line[pl_id] = {
                        "production_line_id": pl_id,
                        "production_line_name": pl_name,
                        "jobs": [],
                        "machines": [],
                    }

                # Criar UM job falso para a parada programada (não um job por máquina)
                # O job terá todas as máquinas da linha, mas apenas a máquina parada terá production_time calculado
                machines_data: List[Dict] = []
                for m_id, m in machines_in_line.items():
                    # Se for a máquina da parada, usa o production_time calculado
                    # Se for outra máquina, usa 99999
                    if m_id == machine_id:
                        machine_production_time = production_time_hours
                    else:
                        machine_production_time = 99999.0
                    
                    machines_data.append({
                        "machine_id": m.id,
                        "machine_name": m.name,
                        "availability": None,
                        "available_factor": None,
                        "cycle_time": None,
                        "cycle_bottleneck": None,
                        "production_time": machine_production_time,
                    })

                # row_data com tudo que veio do JSON, para debug
                row_serializable: Dict[str, Optional[str]] = {}
                for k, v in stop.items():
                    if isinstance(v, (datetime, pd.Timestamp)):
                        row_serializable[k] = v.isoformat()
                    else:
                        row_serializable[k] = None if v is None else str(v)

                fake_job = {
                    "composition_line_id": None,
                    "mold_id": None,
                    "mold_name": None,
                    "product_id": None,
                    "product_name": reason,  # reason vai no product_name
                    "demand": None,
                    "scrap_percent": None,
                    "closed_cavity_risk_percent": None,
                    "scrap_factor": None,
                    "demand_with_scrap": None,
                    "post_injection_cycle_time": None,
                    "total_post_injection_time": None,
                    "deadline_hours": None,
                    "deadline_in_injection": deadline_in_injection,  # Calculado para a máquina parada
                    "processing_time_by_machine": machines_data,  # RENOMEADO de "machines"
                    "row_data": row_serializable,
                }

                jobs_by_line[pl_id]["jobs"].append(fake_job)

                # Atualizar lista de máquinas únicas da linha
                for machine_data in machines_data:
                    m_id = machine_data["machine_id"]
                    if m_id not in [m["machine_id"] for m in jobs_by_line[pl_id]["machines"]]:
                        jobs_by_line[pl_id]["machines"].append(
                            {
                                "machine_id": m_id,
                                "machine_name": machine_data["machine_name"],
                                "availability": None,
                            }
                        )

            except Exception as exc:
                errors.append(f"ProgrammedStop {idx}: Erro ao processar - {exc}")
                continue

    return {
        "jobs_by_line": jobs_by_line,
        "errors": errors,
        "total_jobs": sum(len(line["jobs"]) for line in jobs_by_line.values()),
        "total_lines": len(jobs_by_line),
    }







