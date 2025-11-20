from typing import List, Optional
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

