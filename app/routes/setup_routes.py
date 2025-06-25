from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.setup import Setup
from app.schemas.setup_schema import (SetupResumeResponse, ProductResume, SetupTrocaResponse, SetupTrocaCreate,
                                      SetupBatchCreate, SetupBatchItem, SetupTrocaUpdate)

from app.models.product import Product
from sqlalchemy.orm import joinedload

router = APIRouter(prefix="/setup_trocas")

@router.post("/", response_model=SetupTrocaResponse)
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

@router.put("/{setup_id}", response_model=SetupTrocaResponse)
def update_setup(setup_id: int, setup: SetupTrocaUpdate, db: Session = Depends(get_db)):
    db_setup = db.query(Setup).get(setup_id)
    if not db_setup:
        raise HTTPException(status_code=404, detail="Setup not found")
    for key, value in setup.model_dump().items():
        setattr(db_setup, key, value)
    db.commit()
    db.refresh(db_setup)
    return db_setup

@router.delete("/{setup_id}")
def delete_setup(setup_id: int, db: Session = Depends(get_db)):
    db_setup = db.query(Setup).get(setup_id)
    if not db_setup:
        raise HTTPException(status_code=404, detail="Setup not found")
    db.delete(db_setup)
    db.commit()
    return {"message": "Setup deleted"}

@router.post("/batch", response_model=dict)
def create_batch_setups(data: SetupBatchCreate, db: Session = Depends(get_db)):
    # Verifica se o produto referência existe
    product_ref = db.query(Product).get(data.product_ref)
    if not product_ref:
        raise HTTPException(status_code=404, detail="Produto de referência não encontrado")

    # Cadastra ele com ele mesmo (tempo = 0)
    if not db.query(Setup).filter_by(from_product=data.product_ref, to_product=data.product_ref).first():
        db.add(Setup(from_product=data.product_ref, to_product=data.product_ref, setup_time=0))

    for item in data.setups:
        # Verifica se o produto destino existe
        product_para = db.query(Product).get(item.product_id)
        if not product_para:
            raise HTTPException(status_code=404, detail=f"Produto destino {item.product_id} não encontrado")

        # Cadastra se não existir
        for de, para in [(data.product_ref, item.product_id), (item.product_id, data.product_ref)]:
            if not db.query(Setup).filter_by(from_product=de, to_product=para).first():
                db.add(Setup(from_product=de, to_product=para, setup_time=item.setup_time))

    db.commit()
    return {"message": "Setups cadastrados com sucesso"}

@router.get("/produto/{product_id}/resumo", response_model=list[SetupResumeResponse])
def get_setups_simplificado(product_id: int, db: Session = Depends(get_db)):
    setups = db.query(Setup).options(
        joinedload(Setup.to_product_rel)
    ).filter_by(from_product=product_id).all()

    return [
        SetupResumeResponse(
            setup_time=s.setup_time,
            pair_product=ProductResume(
                id=s.to_product_rel.id,
                name=s.to_product_rel.name
            )
        )
        for s in setups
    ]