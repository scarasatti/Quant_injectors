from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.regular_shift import RegularShift
from app.schemas.regular_shift_schema import (
    RegularShiftCreate,
    RegularShiftUpdate,
    RegularShiftResponse,
    DiaSemana,
)

router = APIRouter(prefix="/turnos-regulares", tags=["Turnos Regulares"])


@router.post("", response_model=RegularShiftResponse)
def create_or_update_regular_shift(
    shift: RegularShiftCreate, db: Session = Depends(get_db)
):
    existing_shift = (
        db.query(RegularShift)
        .filter(RegularShift.dia_semana == shift.dia_semana)
        .first()
    )

    if existing_shift:
        existing_shift.manha = shift.manha
        existing_shift.tarde = shift.tarde
        existing_shift.noite = shift.noite
        existing_shift.frequencia = shift.frequencia
        db.commit()
        db.refresh(existing_shift)
        return existing_shift

    new_shift = RegularShift(**shift.model_dump())
    db.add(new_shift)
    db.commit()
    db.refresh(new_shift)
    return new_shift


@router.get("", response_model=list[RegularShiftResponse])
def list_regular_shifts(db: Session = Depends(get_db)):
    return db.query(RegularShift).all()


@router.get("/dia/{dia_semana}", response_model=RegularShiftResponse)
def get_regular_shift_by_dia(dia_semana: DiaSemana, db: Session = Depends(get_db)):
    shift = (
        db.query(RegularShift)
        .filter(RegularShift.dia_semana == dia_semana)
        .first()
    )
    if not shift:
        raise HTTPException(status_code=404, detail="Turno não encontrado")
    return shift


@router.get("/{shift_id}", response_model=RegularShiftResponse)
def get_regular_shift(shift_id: int, db: Session = Depends(get_db)):
    shift = db.query(RegularShift).get(shift_id)
    if not shift:
        raise HTTPException(status_code=404, detail="Turno não encontrado")
    return shift


@router.put("/{shift_id}", response_model=RegularShiftResponse)
def update_regular_shift(
    shift_id: int, shift: RegularShiftUpdate, db: Session = Depends(get_db)
):
    db_shift = db.query(RegularShift).get(shift_id)
    if not db_shift:
        raise HTTPException(status_code=404, detail="Turno não encontrado")

    update_data = shift.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_shift, key, value)

    db.commit()
    db.refresh(db_shift)
    return db_shift


@router.delete("/{shift_id}")
def delete_regular_shift(shift_id: int, db: Session = Depends(get_db)):
    db_shift = db.query(RegularShift).get(shift_id)
    if not db_shift:
        raise HTTPException(status_code=404, detail="Turno não encontrado")
    db.delete(db_shift)
    db.commit()
    return {"message": "Turno regular removido"}











