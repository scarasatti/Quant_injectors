from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from app.database import get_db
from app.models.setup import Setup
from app.models.production_line import ProductionLine
from app.models.composition_line import CompositionLine
from app.models.machine import Machine
from app.schemas.setup_schema import SetupResumeResponse, CompositionLineResume

router = APIRouter(prefix="/setup-matrix", tags=["Setup Matrix"])

def generate_setup_name(mold_name: str, product_name: str) -> str:
    """Gera o nome do setup: concatenação de mold.name + product.name"""
    return f"{mold_name} {product_name}"

@router.post("/production-line/{production_line_id}/generate")
def generate_setup_matrix(production_line_id: int, db: Session = Depends(get_db)):
    """
    Gera automaticamente a matriz de setup para uma linha de produção.
    Cria setups para todas as combinações de composition lines da linha de produção
    e todas as máquinas associadas.
    """
    # Buscar a linha de produção
    production_line = db.query(ProductionLine).options(
        joinedload(ProductionLine.composition_lines).joinedload(CompositionLine.mold),
        joinedload(ProductionLine.composition_lines).joinedload(CompositionLine.product),
        joinedload(ProductionLine.composition_lines).joinedload(CompositionLine.machines)
    ).filter(ProductionLine.id == production_line_id).first()
    
    if not production_line:
        raise HTTPException(status_code=404, detail="Production line not found")
    
    composition_lines = production_line.composition_lines
    if len(composition_lines) == 0:
        raise HTTPException(
            status_code=400,
            detail="Production line has no composition lines. Please add composition lines first."
        )
    
    created_count = 0
    updated_count = 0
    
    # Gerar matriz: para cada combinação de composition lines
    for from_cl in composition_lines:
        from_name = generate_setup_name(from_cl.mold.name, from_cl.product.name)
        
        for to_cl in composition_lines:
            # Verificar se já existe
            existing_setup = db.query(Setup).filter(
                Setup.production_line_id == production_line_id,
                Setup.from_composition_line_id == from_cl.id,
                Setup.to_composition_line_id == to_cl.id
            ).first()
            
            if existing_setup:
                # Atualizar apenas o nome se necessário
                if existing_setup.name != from_name:
                    existing_setup.name = from_name
                    updated_count += 1
                continue
            
            # Criar novo setup
            # Tempo padrão: 0 se for o mesmo (from == to), senão 0 (será atualizado depois)
            default_time = 0 if from_cl.id == to_cl.id else 0
            
            new_setup = Setup(
                production_line_id=production_line_id,
                from_composition_line_id=from_cl.id,
                to_composition_line_id=to_cl.id,
                name=from_name,
                setup_time=default_time
            )
            db.add(new_setup)
            created_count += 1
    
    db.commit()
    
    return {
        "message": f"Setup matrix generated for production line '{production_line.name}'",
        "production_line_id": production_line_id,
        "composition_lines_count": len(composition_lines),
        "setups_created": created_count,
        "setups_updated": updated_count,
        "total_combinations": len(composition_lines) * len(composition_lines)
    }

@router.get("/production-line/{production_line_id}", response_model=list[SetupResumeResponse])
def get_setup_matrix(production_line_id: int, db: Session = Depends(get_db)):
    """
    Retorna a matriz de setup de uma linha de produção.
    """
    production_line = db.query(ProductionLine).get(production_line_id)
    if not production_line:
        raise HTTPException(status_code=404, detail="Production line not found")
    
    setups = db.query(Setup).options(
        joinedload(Setup.from_composition_line).joinedload(CompositionLine.mold),
        joinedload(Setup.from_composition_line).joinedload(CompositionLine.product),
        joinedload(Setup.to_composition_line).joinedload(CompositionLine.mold),
        joinedload(Setup.to_composition_line).joinedload(CompositionLine.product)
    ).filter(Setup.production_line_id == production_line_id).all()
    
    return [
        SetupResumeResponse(
            id=s.id,
            name=s.name,
            setup_time=s.setup_time,
            from_composition_line=CompositionLineResume(
                id=s.from_composition_line.id,
                mold_name=s.from_composition_line.mold.name,
                product_name=s.from_composition_line.product.name,
                name=generate_setup_name(s.from_composition_line.mold.name, s.from_composition_line.product.name)
            ),
            to_composition_line=CompositionLineResume(
                id=s.to_composition_line.id,
                mold_name=s.to_composition_line.mold.name,
                product_name=s.to_composition_line.product.name,
                name=generate_setup_name(s.to_composition_line.mold.name, s.to_composition_line.product.name)
            )
        )
        for s in setups
    ]

