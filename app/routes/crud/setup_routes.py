from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from app.database import get_db
from app.models.setup import Setup
from app.models.composition_line import CompositionLine
from app.models.production_line import ProductionLine
from app.models.product import Product
from app.models.mold import Mold
from app.models.mold_product import MoldProduct
from app.schemas.setup_schema import (
    SetupResumeResponse, CompositionLineResume,
    SetupTrocaResponse, SetupTrocaCreate, SetupTrocaUpdate,
    SetupBatchUpdateRequest, SetupBatchUpdateItem, ProductResume, MoldResume
)

router = APIRouter(prefix="/setup_trocas")

def get_or_create_composition_line(product_id: int, mold_id: int, db: Session) -> CompositionLine:
    """
    Busca uma composition_line baseada em product_id + mold_id.
    Valida que o produto está associado ao molde.
    """
    # Validar que o produto existe
    product = db.query(Product).get(product_id)
    if not product:
        raise HTTPException(status_code=404, detail=f"Produto com ID {product_id} não encontrado")
    
    # Validar que o molde existe
    mold = db.query(Mold).get(mold_id)
    if not mold:
        raise HTTPException(status_code=404, detail=f"Molde com ID {mold_id} não encontrado")
    
    # Validar que o produto está associado ao molde
    mold_product = db.query(MoldProduct).filter_by(
        product_id=product_id,
        mold_id=mold_id
    ).first()
    
    if not mold_product:
        raise HTTPException(
            status_code=400, 
            detail=f"Produto '{product.name}' não está associado ao molde '{mold.name}'"
        )
    
    # Buscar composition_line existente
    composition_line = db.query(CompositionLine).filter_by(
        product_id=product_id,
        mold_id=mold_id
    ).first()
    
    if not composition_line:
        raise HTTPException(
            status_code=404,
            detail=f"Composition line não encontrada para produto '{product.name}' e molde '{mold.name}'. "
                   f"Por favor, crie a composition line primeiro."
        )
    
    return composition_line

@router.put("/batch", response_model=list[SetupTrocaResponse])
def update_setups_batch(request: SetupBatchUpdateRequest, db: Session = Depends(get_db)):
    updated_setups = []

    for item in request.updates:
        db_setup = db.query(Setup).get(item.id)
        if not db_setup:
            continue

        old_from = db_setup.from_composition_line_id
        old_to = db_setup.to_composition_line_id

        db_setup.setup_time = item.setup_time

        # Atualiza automaticamente o setup espelhado (inverso)
        # Se Produto1+Molde1 → Produto2+Molde2 = 60s, então Produto2+Molde2 → Produto1+Molde1 = 60s automaticamente
        if old_from != old_to:  # Não atualizar espelho se for o mesmo
            espelhado = db.query(Setup).filter(
                Setup.production_line_id == db_setup.production_line_id,
                Setup.from_composition_line_id == old_to,
                Setup.to_composition_line_id == old_from
            ).first()

            if espelhado:
                espelhado.setup_time = item.setup_time
            else:
                # Se o espelho não existe, cria automaticamente
                # Buscar composition lines para gerar o nome
                to_cl = db.query(CompositionLine).options(
                    joinedload(CompositionLine.mold),
                    joinedload(CompositionLine.product)
                ).get(old_to)
                if to_cl:
                    inverse_setup_name = f"{to_cl.mold.name} {to_cl.product.name}"
                    inverse_setup = Setup(
                        production_line_id=db_setup.production_line_id,
                        from_composition_line_id=old_to,
                        to_composition_line_id=old_from,
                        name=inverse_setup_name,
                        setup_time=item.setup_time
                    )
                    db.add(inverse_setup)

        updated_setups.append(db_setup)

    db.commit()
    
    # Buscar informações completas para as respostas
    setup_ids = [s.id for s in updated_setups]
    setups_with_details = db.query(Setup).options(
        joinedload(Setup.from_composition_line).joinedload(CompositionLine.product),
        joinedload(Setup.from_composition_line).joinedload(CompositionLine.mold),
        joinedload(Setup.to_composition_line).joinedload(CompositionLine.product),
        joinedload(Setup.to_composition_line).joinedload(CompositionLine.mold)
    ).filter(Setup.id.in_(setup_ids)).all()
    
    return [
        SetupTrocaResponse(
            id=s.id,
            production_line_id=s.production_line_id,
            from_composition_line_id=s.from_composition_line_id,
            to_composition_line_id=s.to_composition_line_id,
            name=s.name,
            setup_time=s.setup_time,
            from_product=ProductResume(id=s.from_composition_line.product.id, name=s.from_composition_line.product.name),
            from_mold=MoldResume(id=s.from_composition_line.mold.id, name=s.from_composition_line.mold.name),
            to_product=ProductResume(id=s.to_composition_line.product.id, name=s.to_composition_line.product.name),
            to_mold=MoldResume(id=s.to_composition_line.mold.id, name=s.to_composition_line.mold.name)
        )
        for s in setups_with_details
    ]

@router.post("", response_model=SetupTrocaResponse)
def create_setup(setup: SetupTrocaCreate, db: Session = Depends(get_db)):
    # Validar que a production line existe
    production_line = db.query(ProductionLine).get(setup.production_line_id)
    if not production_line:
        raise HTTPException(status_code=404, detail="Production line not found")
    
    # Validar que as composition lines existem e pertencem à production line
    from_cl = db.query(CompositionLine).filter(
        CompositionLine.id == setup.from_composition_line_id,
        CompositionLine.production_line_id == setup.production_line_id
    ).first()
    if not from_cl:
        raise HTTPException(status_code=404, detail="From composition line not found or does not belong to this production line")
    
    to_cl = db.query(CompositionLine).filter(
        CompositionLine.id == setup.to_composition_line_id,
        CompositionLine.production_line_id == setup.production_line_id
    ).first()
    if not to_cl:
        raise HTTPException(status_code=404, detail="To composition line not found or does not belong to this production line")

    # Verificar se já existe o setup direto
    existing = db.query(Setup).filter(
        Setup.production_line_id == setup.production_line_id,
        Setup.from_composition_line_id == setup.from_composition_line_id,
        Setup.to_composition_line_id == setup.to_composition_line_id
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="Setup já cadastrado para esta combinação")

    # Gerar o nome do setup (mold.name + product.name do from_composition_line)
    setup_name = f"{from_cl.mold.name} {from_cl.product.name}"

    # Criar o setup direto
    db_setup = Setup(
        production_line_id=setup.production_line_id,
        from_composition_line_id=setup.from_composition_line_id,
        to_composition_line_id=setup.to_composition_line_id,
        name=setup_name,
        setup_time=setup.setup_time
    )
    db.add(db_setup)

    # Criar automaticamente o setup inverso (espelho) se não existir
    # Se Produto1+Molde1 → Produto2+Molde2 = 60s, então Produto2+Molde2 → Produto1+Molde1 = 60s automaticamente
    if setup.from_composition_line_id != setup.to_composition_line_id:  # Não criar espelho se for o mesmo
        existing_inverse = db.query(Setup).filter(
            Setup.production_line_id == setup.production_line_id,
            Setup.from_composition_line_id == setup.to_composition_line_id,
            Setup.to_composition_line_id == setup.from_composition_line_id
        ).first()

        if not existing_inverse:
            # Gerar o nome do setup inverso (mold.name + product.name do to_composition_line)
            inverse_setup_name = f"{to_cl.mold.name} {to_cl.product.name}"
            inverse_setup = Setup(
                production_line_id=setup.production_line_id,
                from_composition_line_id=setup.to_composition_line_id,
                to_composition_line_id=setup.from_composition_line_id,
                name=inverse_setup_name,
                setup_time=setup.setup_time  # Mesmo tempo do setup direto
            )
            db.add(inverse_setup)

    db.commit()
    db.refresh(db_setup)
    
    # Buscar informações completas para a resposta
    db_setup = db.query(Setup).options(
        joinedload(Setup.from_composition_line).joinedload(CompositionLine.product),
        joinedload(Setup.from_composition_line).joinedload(CompositionLine.mold),
        joinedload(Setup.to_composition_line).joinedload(CompositionLine.product),
        joinedload(Setup.to_composition_line).joinedload(CompositionLine.mold)
    ).get(db_setup.id)
    
    return SetupTrocaResponse(
        id=db_setup.id,
        production_line_id=db_setup.production_line_id,
        from_composition_line_id=db_setup.from_composition_line_id,
        to_composition_line_id=db_setup.to_composition_line_id,
        name=db_setup.name,
        setup_time=db_setup.setup_time,
        from_product=ProductResume(id=db_setup.from_composition_line.product.id, name=db_setup.from_composition_line.product.name),
        from_mold=MoldResume(id=db_setup.from_composition_line.mold.id, name=db_setup.from_composition_line.mold.name),
        to_product=ProductResume(id=db_setup.to_composition_line.product.id, name=db_setup.to_composition_line.product.name),
        to_mold=MoldResume(id=db_setup.to_composition_line.mold.id, name=db_setup.to_composition_line.mold.name)
    )


@router.get("/", response_model=list[SetupTrocaResponse])
def list_setups(db: Session = Depends(get_db)):
    setups = db.query(Setup).options(
        joinedload(Setup.from_composition_line).joinedload(CompositionLine.product),
        joinedload(Setup.from_composition_line).joinedload(CompositionLine.mold),
        joinedload(Setup.to_composition_line).joinedload(CompositionLine.product),
        joinedload(Setup.to_composition_line).joinedload(CompositionLine.mold)
    ).all()
    
    return [
        SetupTrocaResponse(
            id=s.id,
            production_line_id=s.production_line_id,
            from_composition_line_id=s.from_composition_line_id,
            to_composition_line_id=s.to_composition_line_id,
            name=s.name,
            setup_time=s.setup_time,
            from_product=ProductResume(id=s.from_composition_line.product.id, name=s.from_composition_line.product.name),
            from_mold=MoldResume(id=s.from_composition_line.mold.id, name=s.from_composition_line.mold.name),
            to_product=ProductResume(id=s.to_composition_line.product.id, name=s.to_composition_line.product.name),
            to_mold=MoldResume(id=s.to_composition_line.mold.id, name=s.to_composition_line.mold.name)
        )
        for s in setups
    ]

@router.get("/{setup_id}", response_model=SetupTrocaResponse)
def get_setup(setup_id: int, db: Session = Depends(get_db)):
    setup = db.query(Setup).options(
        joinedload(Setup.from_composition_line).joinedload(CompositionLine.product),
        joinedload(Setup.from_composition_line).joinedload(CompositionLine.mold),
        joinedload(Setup.to_composition_line).joinedload(CompositionLine.product),
        joinedload(Setup.to_composition_line).joinedload(CompositionLine.mold)
    ).get(setup_id)
    
    if not setup:
        raise HTTPException(status_code=404, detail="Setup not found")
    
    return SetupTrocaResponse(
        id=setup.id,
        production_line_id=setup.production_line_id,
        from_composition_line_id=setup.from_composition_line_id,
        to_composition_line_id=setup.to_composition_line_id,
        name=setup.name,
        setup_time=setup.setup_time,
        from_product=ProductResume(id=setup.from_composition_line.product.id, name=setup.from_composition_line.product.name),
        from_mold=MoldResume(id=setup.from_composition_line.mold.id, name=setup.from_composition_line.mold.name),
        to_product=ProductResume(id=setup.to_composition_line.product.id, name=setup.to_composition_line.product.name),
        to_mold=MoldResume(id=setup.to_composition_line.mold.id, name=setup.to_composition_line.mold.name)
    )

@router.put("/{setup_id}", response_model=SetupTrocaResponse)
def update_setup(setup_id: int, setup_update: SetupTrocaUpdate, db: Session = Depends(get_db)):
    db_setup = db.query(Setup).get(setup_id)
    if not db_setup:
        raise HTTPException(status_code=404, detail="Setup not found")
    
    # Validar que a production line existe
    production_line = db.query(ProductionLine).get(setup_update.production_line_id)
    if not production_line:
        raise HTTPException(status_code=404, detail="Production line not found")
    
    # Validar que as composition lines existem e pertencem à production line
    from_cl = db.query(CompositionLine).filter(
        CompositionLine.id == setup_update.from_composition_line_id,
        CompositionLine.production_line_id == setup_update.production_line_id
    ).first()
    if not from_cl:
        raise HTTPException(status_code=404, detail="From composition line not found or does not belong to this production line")
    
    to_cl = db.query(CompositionLine).filter(
        CompositionLine.id == setup_update.to_composition_line_id,
        CompositionLine.production_line_id == setup_update.production_line_id
    ).first()
    if not to_cl:
        raise HTTPException(status_code=404, detail="To composition line not found or does not belong to this production line")

    # Guardar valores antigos para atualizar o inverso
    old_from = db_setup.from_composition_line_id
    old_to = db_setup.to_composition_line_id

    # Gerar o novo nome do setup
    setup_name = f"{from_cl.mold.name} {from_cl.product.name}"

    # Atualizar o setup
    db_setup.production_line_id = setup_update.production_line_id
    db_setup.from_composition_line_id = setup_update.from_composition_line_id
    db_setup.to_composition_line_id = setup_update.to_composition_line_id
    db_setup.name = setup_name
    db_setup.setup_time = setup_update.setup_time

    # Atualizar automaticamente o setup inverso (espelho)
    # Se Produto1+Molde1 → Produto2+Molde2 = 60s, então Produto2+Molde2 → Produto1+Molde1 = 60s automaticamente
    if setup_update.from_composition_line_id != setup_update.to_composition_line_id:
        inverse_setup = db.query(Setup).filter(
            Setup.production_line_id == setup_update.production_line_id,
            Setup.from_composition_line_id == setup_update.to_composition_line_id,
            Setup.to_composition_line_id == setup_update.from_composition_line_id
        ).first()

        if inverse_setup:
            # Atualiza o inverso também
            inverse_setup_name = f"{to_cl.mold.name} {to_cl.product.name}"
            inverse_setup.name = inverse_setup_name
            inverse_setup.setup_time = setup_update.setup_time
        else:
            # Se o inverso não existe, cria automaticamente
            inverse_setup_name = f"{to_cl.mold.name} {to_cl.product.name}"
            new_inverse = Setup(
                production_line_id=setup_update.production_line_id,
                from_composition_line_id=setup_update.to_composition_line_id,
                to_composition_line_id=setup_update.from_composition_line_id,
                name=inverse_setup_name,
                setup_time=setup_update.setup_time
            )
            db.add(new_inverse)

    db.commit()
    db.refresh(db_setup)
    
    # Buscar informações completas para a resposta
    db_setup = db.query(Setup).options(
        joinedload(Setup.from_composition_line).joinedload(CompositionLine.product),
        joinedload(Setup.from_composition_line).joinedload(CompositionLine.mold),
        joinedload(Setup.to_composition_line).joinedload(CompositionLine.product),
        joinedload(Setup.to_composition_line).joinedload(CompositionLine.mold)
    ).get(db_setup.id)
    
    return SetupTrocaResponse(
        id=db_setup.id,
        production_line_id=db_setup.production_line_id,
        from_composition_line_id=db_setup.from_composition_line_id,
        to_composition_line_id=db_setup.to_composition_line_id,
        name=db_setup.name,
        setup_time=db_setup.setup_time,
        from_product=ProductResume(id=db_setup.from_composition_line.product.id, name=db_setup.from_composition_line.product.name),
        from_mold=MoldResume(id=db_setup.from_composition_line.mold.id, name=db_setup.from_composition_line.mold.name),
        to_product=ProductResume(id=db_setup.to_composition_line.product.id, name=db_setup.to_composition_line.product.name),
        to_mold=MoldResume(id=db_setup.to_composition_line.mold.id, name=db_setup.to_composition_line.mold.name)
    )

@router.delete("/{setup_id}")
def delete_setup(setup_id: int, db: Session = Depends(get_db)):
    db_setup = db.query(Setup).get(setup_id)
    if not db_setup:
        raise HTTPException(status_code=404, detail="Setup not found")
    
    # Guardar valores para deletar o inverso também
    from_id = db_setup.from_composition_line_id
    to_id = db_setup.to_composition_line_id
    
    # Deletar o setup
    db.delete(db_setup)
    
    # Deletar automaticamente o setup inverso (espelho) se existir
    # Se deletar Produto1+Molde1 → Produto2+Molde2, também deleta Produto2+Molde2 → Produto1+Molde1
    if from_id != to_id:  # Não deletar se for o mesmo
        inverse_setup = db.query(Setup).filter(
            Setup.production_line_id == db_setup.production_line_id,
            Setup.from_composition_line_id == to_id,
            Setup.to_composition_line_id == from_id
        ).first()
        
        if inverse_setup:
            db.delete(inverse_setup)
    
    db.commit()
    return {"message": "Setup deleted"}


@router.get("/composition-line/{composition_line_id}/resumo", response_model=list[SetupResumeResponse])
def get_setups_simplificado(composition_line_id: int, db: Session = Depends(get_db)):
    setups = db.query(Setup).options(
        joinedload(Setup.from_composition_line).joinedload(CompositionLine.mold),
        joinedload(Setup.from_composition_line).joinedload(CompositionLine.product),
        joinedload(Setup.to_composition_line).joinedload(CompositionLine.mold),
        joinedload(Setup.to_composition_line).joinedload(CompositionLine.product)
    ).filter_by(from_composition_line_id=composition_line_id).all()

    return [
        SetupResumeResponse(
            id=s.id,
            name=s.name,
            setup_time=s.setup_time,
            from_composition_line=CompositionLineResume(
                id=s.from_composition_line.id,
                mold_name=s.from_composition_line.mold.name,
                product_name=s.from_composition_line.product.name,
                name=f"{s.from_composition_line.mold.name} {s.from_composition_line.product.name}"
            ),
            to_composition_line=CompositionLineResume(
                id=s.to_composition_line.id,
                mold_name=s.to_composition_line.mold.name,
                product_name=s.to_composition_line.product.name,
                name=f"{s.to_composition_line.mold.name} {s.to_composition_line.product.name}"
            )
        )
        for s in setups
    ]



