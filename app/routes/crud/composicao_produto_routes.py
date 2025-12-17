from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from app.database import get_db
from app.models.product_composition import ProductComposition
from app.models.product import Product
from app.models.raw_material import RawMaterial
from app.schemas.composicao_produto_schema import ComposicaoProdutoCreate, ComposicaoProdutoUpdate, ComposicaoProdutoResponse

router = APIRouter(prefix="/composicao-produto", tags=["Composição de Produtos"])

@router.post("", response_model=ComposicaoProdutoResponse)
def create_composicao_produto(composicao: ComposicaoProdutoCreate, db: Session = Depends(get_db)):
    # Verificar se o produto existe
    produto = db.query(Product).get(composicao.produto_id)
    if not produto:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    
    # Verificar se a matéria prima existe
    materia_prima = db.query(RawMaterial).get(composicao.materia_prima_id)
    if not materia_prima:
        raise HTTPException(status_code=404, detail="Matéria prima não encontrada")
    
    # Verificar se já existe uma composição com o mesmo produto e matéria prima
    existing = db.query(ProductComposition).filter(
        ProductComposition.produto_id == composicao.produto_id,
        ProductComposition.materia_prima_id == composicao.materia_prima_id
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=400, 
            detail="Já existe uma composição para este produto com esta matéria prima"
        )
    
    db_composicao = ProductComposition(**composicao.model_dump())
    db.add(db_composicao)
    db.commit()
    db.refresh(db_composicao)
    return db_composicao

@router.get("/", response_model=list[ComposicaoProdutoResponse])
def list_composicao_produto(db: Session = Depends(get_db)):
    composicoes = db.query(ProductComposition).options(
        joinedload(ProductComposition.produto),
        joinedload(ProductComposition.materia_prima)
    ).all()
    return composicoes

@router.get("/produto/{produto_id}", response_model=list[ComposicaoProdutoResponse])
def get_composicao_by_produto(produto_id: int, db: Session = Depends(get_db)):
    composicoes = db.query(ProductComposition).options(
        joinedload(ProductComposition.produto),
        joinedload(ProductComposition.materia_prima)
    ).filter(ProductComposition.produto_id == produto_id).all()
    return composicoes

@router.get("/{composicao_id}", response_model=ComposicaoProdutoResponse)
def get_composicao_produto(composicao_id: int, db: Session = Depends(get_db)):
    composicao = db.query(ProductComposition).options(
        joinedload(ProductComposition.produto),
        joinedload(ProductComposition.materia_prima)
    ).filter(ProductComposition.id == composicao_id).first()
    if not composicao:
        raise HTTPException(status_code=404, detail="Composição não encontrada")
    return composicao

@router.put("/{composicao_id}", response_model=ComposicaoProdutoResponse)
def update_composicao_produto(composicao_id: int, composicao: ComposicaoProdutoUpdate, db: Session = Depends(get_db)):
    db_composicao = db.query(ProductComposition).get(composicao_id)
    if not db_composicao:
        raise HTTPException(status_code=404, detail="Composição não encontrada")
    
    # Verificar se o produto existe
    produto = db.query(Product).get(composicao.produto_id)
    if not produto:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    
    # Verificar se a matéria prima existe
    materia_prima = db.query(RawMaterial).get(composicao.materia_prima_id)
    if not materia_prima:
        raise HTTPException(status_code=404, detail="Matéria prima não encontrada")
    
    # Verificar se já existe outra composição com o mesmo produto e matéria prima
    existing = db.query(ProductComposition).filter(
        ProductComposition.produto_id == composicao.produto_id,
        ProductComposition.materia_prima_id == composicao.materia_prima_id,
        ProductComposition.id != composicao_id
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=400, 
            detail="Já existe uma composição para este produto com esta matéria prima"
        )
    
    for key, value in composicao.model_dump().items():
        setattr(db_composicao, key, value)
    db.commit()
    db.refresh(db_composicao)
    return db_composicao

@router.delete("/{composicao_id}")
def delete_composicao_produto(composicao_id: int, db: Session = Depends(get_db)):
    db_composicao = db.query(ProductComposition).get(composicao_id)
    if not db_composicao:
        raise HTTPException(status_code=404, detail="Composição não encontrada")
    
    db.delete(db_composicao)
    db.commit()
    return {"message": "Composição deletada com sucesso"}

