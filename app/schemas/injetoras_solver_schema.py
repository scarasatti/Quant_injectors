from typing import List, Optional
from datetime import date, time, datetime
from pydantic import BaseModel, Field


class ProcessingEntry(BaseModel):
    job: int
    machine: int
    time: float = Field(ge=0, description="Tempo de processamento para (job, máquina)")


class SetupEntry(BaseModel):
    predecessor: int = Field(alias="from_job")
    successor: int = Field(alias="to_job")
    machine: int
    time: float = Field(ge=0, description="Tempo de setup entre (i, j, máquina)")


class DueEntry(BaseModel):
    job: int
    time: float = Field(ge=0, description="Prazo (due date) do job")


class PriorityEntry(BaseModel):
    job: int
    value: float = Field(ge=0, description="Peso/prioridade do job")


class InjetorasRequest(BaseModel):
    jobs: Optional[List[int]] = Field(
        default=None,
        description="IDs dos jobs considerados pelo modelo. Se omitido, usa os padrões."
    )
    machines: Optional[List[int]] = Field(
        default=None,
        description="IDs das máquinas disponíveis. Se omitido, usa os padrões."
    )
    processing: Optional[List[ProcessingEntry]] = Field(
        default=None,
        description="Tempos de processamento. Se omitido, usa valores padrão."
    )
    due: Optional[List[DueEntry]] = Field(
        default=None,
        description="Prazos por job. Se omitido, usa valores padrão."
    )
    priority: Optional[List[PriorityEntry]] = Field(
        default=None,
        description="Prioridades por job. Se omitido, usa valores padrão."
    )
    setup: Optional[List[SetupEntry]] = Field(
        default=None,
        description="Tempos de setup entre pares de jobs por máquina. Se omitido, usa valores padrão."
    )
    dummy: Optional[int] = Field(
        default=0,
        description="Job dummy utilizado para ancorar o fluxo. Use None para desativar."
    )

    class Config:
        allow_population_by_field_name = True


class MachineStateEntry(BaseModel):
    """
    Estado atual de uma máquina antes de rodar o solver.
    
    Representa um job que já está em execução na máquina, ocupando capacidade
    por um certo tempo restante.
    """
    
    production_line_id: int = Field(..., description="ID da linha de produção (Linha)")
    machine_id: int = Field(..., description="ID da máquina")
    used: bool = Field(..., description="Se a máquina está sendo utilizada neste momento")
    
    mold_id: Optional[int] = Field(default=None, description="ID do molde atual")
    product_id: Optional[int] = Field(default=None, description="ID do produto atual")
    
    completed: bool = Field(
        default=False,
        description="Se o job atual já foi concluído na máquina",
    )
    
    order_number: Optional[str] = Field(
        default=None, description="Número do pedido associado"
    )
    client_name: Optional[str] = Field(
        default=None, description="Nome do cliente"
    )
    
    remaining_injection_hours: float = Field(
        ge=0,
        description="Tempo restante na injetora (minutos)",
    )
    remaining_post_injection_hours: float = Field(
        ge=0,
        description="Tempo restante de produção pós-injetora (minutos)",
    )
    
    demand: Optional[int] = Field(
        default=None,
        ge=0,
        description="Demanda restante do pedido (peças)",
    )
    billing_value: Optional[float] = Field(
        default=None,
        ge=0,
        description="Valor a ser faturado para este pedido",
    )
    
    billing_deadline_date: Optional[date] = Field(
        default=None,
        description="Data limite do faturamento",
    )
    billing_deadline_time: Optional[time] = Field(
        default=None,
        description="Hora limite do faturamento",
    )


class InjetorasFromJobsRequest(BaseModel):
    """
    Requisição para rodar o solver de injetoras a partir de jobs do banco,
    considerando também o estado atual das máquinas.
    """
    
    job_ids: List[int] = Field(
        ..., description="Lista de IDs de jobs do banco a serem sequenciados"
    )
    sequencing_date: datetime = Field(
        ..., description="Data e hora de início do sequenciamento"
    )
    machine_states: Optional[List[MachineStateEntry]] = Field(
        default=None,
        description=(
            "Estado atual das máquinas (jobs já em execução) antes de rodar o solver."
        ),
    )


class ProgrammedStopRequest(BaseModel):
    """
    Request para criar um job falso de parada programada
    (manutenção preventiva, setup externo, etc.).
    """
    
    reason: str = Field(..., description="Motivo da parada (ex: Manutenção preventiva)")
    machine_id: int = Field(..., description="ID da máquina que será parada")
    
    start_date: date = Field(..., description="Data de início da parada")
    start_time: time = Field(..., description="Hora de início da parada")
    
    end_date: date = Field(..., description="Data de término da parada")
    end_time: time = Field(..., description="Hora de término da parada")
    
    sequencing_date: datetime = Field(
        ...,
        description="Data/hora de início do sequenciamento que vai considerar essa parada",
    )
    machines: List[int] = Field(
        ...,
        description="Lista de IDs de máquinas da linha (para receber 9999 nas que não param)",
    )


