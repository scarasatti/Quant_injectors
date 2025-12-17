from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.machine import Machine
from app.schemas.maquina_schema import MachineCreate, MachineUpdate, MachineResponse

router = APIRouter(prefix="/machines", tags=["Machines"])

@router.post("", response_model=MachineResponse)
def create_machine(machine: MachineCreate, db: Session = Depends(get_db)):
    db_machine = Machine(**machine.model_dump())
    db.add(db_machine)
    db.commit()
    db.refresh(db_machine)
    return db_machine

@router.get("/", response_model=list[MachineResponse])
def list_machines(db: Session = Depends(get_db)):
    return db.query(Machine).all()

@router.get("/{machine_id}", response_model=MachineResponse)
def get_machine(machine_id: int, db: Session = Depends(get_db)):
    machine = db.query(Machine).get(machine_id)
    if not machine:
        raise HTTPException(status_code=404, detail="Machine not found")
    return machine

@router.put("/{machine_id}", response_model=MachineResponse)
def update_machine(machine_id: int, machine: MachineUpdate, db: Session = Depends(get_db)):
    db_machine = db.query(Machine).get(machine_id)
    if not db_machine:
        raise HTTPException(status_code=404, detail="Machine not found")
    for key, value in machine.model_dump().items():
        setattr(db_machine, key, value)
    db.commit()
    db.refresh(db_machine)
    return db_machine

@router.delete("/{machine_id}")
def delete_machine(machine_id: int, db: Session = Depends(get_db)):
    db_machine = db.query(Machine).get(machine_id)
    if not db_machine:
        raise HTTPException(status_code=404, detail="Machine not found")
    db.delete(db_machine)
    db.commit()
    return {"message": "Machine deleted successfully"}




