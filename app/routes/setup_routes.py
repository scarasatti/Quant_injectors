from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.setup import Setup
from app.schemas.setup_schema import (SetupResumeResponse, ProductResume, SetupTrocaResponse, SetupTrocaCreate,
                                      SetupBatchCreate, SetupBatchItem, SetupTrocaUpdate)

from app.models.product import Product
from sqlalchemy.orm import joinedload

router = APIRouter(prefix="/setup_trocas", tags=["SetupTrocas"])

@router.post("/", response_model=SetupTrocaResponse)
def create_setup(setup: SetupTrocaCreate, db: Session = Depends(get_db)):

    existing = db.query(Setup).filter_by(
        produto_de=setup.produto_de,
        produto_para=setup.produto_para
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
    if not db.query(Setup).filter_by(produto_de=data.product_ref, produto_para=data.product_ref).first():
        db.add(Setup(produto_de=data.product_ref, produto_para=data.product_ref, tempo_setup=0))

    for item in data.setups:
        # Verifica se o produto destino existe
        product_para = db.query(Product).get(item.product_id)
        if not product_para:
            raise HTTPException(status_code=404, detail=f"Produto destino {item.product_id} não encontrado")

        # Cadastra se não existir
        for de, para in [(data.product_ref, item.product_id), (item.product_id, data.product_ref)]:
            if not db.query(Setup).filter_by(produto_de=de, produto_para=para).first():
                db.add(Setup(produto_de=de, produto_para=para, tempo_setup=item.tempo_setup))

    db.commit()
    return {"message": "Setups cadastrados com sucesso"}

@router.get("/produto/{product_id}/resumo", response_model=list[SetupResumeResponse])
def get_setups_simplificado(product_id: int, db: Session = Depends(get_db)):
    setups = db.query(Setup).options(
        joinedload(Setup.produto_para_rel)
    ).filter_by(produto_de=product_id).all()

    return [
        SetupResumeResponse(
            tempo_setup=s.tempo_setup,
            produto_destino=ProductResume(
                id=s.produto_para_rel.id,
                name=s.produto_para_rel.name
            )
        )
        for s in setups
    ]