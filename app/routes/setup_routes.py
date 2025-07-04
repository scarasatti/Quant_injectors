from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.setup import Setup
from app.schemas.setup_schema import (SetupResumeResponse, ProductResume, SetupTrocaResponse, SetupTrocaCreate,
                                      SetupBatchCreate, SetupBatchItem, SetupTrocaUpdate,SetupBatchUpdateRequest,
                                      SetupBatchUpdateItem)

from app.models.product import Product
from sqlalchemy.orm import joinedload

router = APIRouter(prefix="/setup_trocas")

@router.put("/batch", response_model=list[SetupTrocaResponse])
def update_setups_batch(request: SetupBatchUpdateRequest, db: Session = Depends(get_db)):
    updated_setups = []

    for item in request.updates:
        db_setup = db.query(Setup).get(item.id)
        if not db_setup:
            continue


        old_from = db_setup.from_product
        old_to = db_setup.to_product


        db_setup.setup_time = item.setup_time


        espelhado = db.query(Setup).filter_by(
            from_product=old_to,
            to_product=old_from
        ).first()

        if espelhado:
            espelhado.setup_time = item.setup_time
        else:
            novo_espelho = Setup(
                from_product=old_to,
                to_product=old_from,
                setup_time=item.setup_time
            )
            db.add(novo_espelho)

        updated_setups.append(db_setup)

    db.commit()
    return updated_setups

@router.post("", response_model=SetupTrocaResponse)
def create_setup(setup: SetupTrocaCreate, db: Session = Depends(get_db)):

    existing = db.query(Setup).filter_by(
        from_product=setup.from_product,
        to_product=setup.to_product
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="Setup já cadastrado")

    db_setup = Setup(**setup.model_dump())
    db.add(db_setup)
    db.commit()
    db.refresh(db_setup)

    return db_setup


@router.get("/", response_model=list[SetupTrocaResponse])
def list_setups(db: Session = Depends(get_db)):
    return db.query(Setup).all()

@router.get("/{setup_id}", response_model=SetupTrocaResponse)
def get_setup(setup_id: int, db: Session = Depends(get_db)):
    setup = db.query(Setup).get(setup_id)
    if not setup:
        raise HTTPException(status_code=404, detail="Setup not found")
    return setup


@router.delete("/{setup_id}")
def delete_setup(setup_id: int, db: Session = Depends(get_db)):
    db_setup = db.query(Setup).get(setup_id)
    if not db_setup:
        raise HTTPException(status_code=404, detail="Setup not found")
    db.delete(db_setup)
    db.commit()
    return {"message": "Setup deleted"}


@router.get("/produto/{product_id}/resumo", response_model=list[SetupResumeResponse])
def get_setups_simplificado(product_id: int, db: Session = Depends(get_db)):
    setups = db.query(Setup).options(
        joinedload(Setup.to_product_rel)
    ).filter_by(from_product=product_id).all()

    return [
        SetupResumeResponse(
            id=s.id,
            setup_time=s.setup_time,
            pair_product=ProductResume(
                id=s.to_product_rel.id,
                name=s.to_product_rel.name
            )
        )
        for s in setups
    ]

