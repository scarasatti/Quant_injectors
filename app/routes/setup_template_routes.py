from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from fastapi.responses import StreamingResponse
import pandas as pd
import io

from app.database import get_db
from app.models.product import Product
from app.models.setup import Setup
from app.auth.auth_bearer import get_current_user
from app.models.user import User

router = APIRouter(prefix="/template", tags=["Templates"])

@router.get("/setup-matrix")
def download_setup_template(db: Session = Depends(get_db),
                            current_user: User = Depends(get_current_user)):
    produtos = db.query(Product).all()
    nomes = [p.name for p in produtos]
    id_por_nome = {p.name: p.id for p in produtos}
    nome_por_id = {p.id: p.name for p in produtos}

    # Cria DataFrame com índice e colunas iguais
    matriz = pd.DataFrame("", index=nomes, columns=nomes)
    matriz.index.name = "De\\Para"

    for nome_de in nomes:
        for nome_para in nomes:
            if nome_de == nome_para:
                matriz.at[nome_de, nome_para] = 0
                continue

            id_de = id_por_nome[nome_de]
            id_para = id_por_nome[nome_para]

            setup = db.query(Setup).filter_by(produto_de=id_de, produto_para=id_para).first()

            if setup:
                matriz.at[nome_de, nome_para] = setup.tempo_setup
            else:
                # Tenta buscar o inverso, apenas para exibição (não altera lógica do modelo)
                setup_inv = db.query(Setup).filter_by(produto_de=id_para, produto_para=id_de).first()
                if setup_inv:
                    matriz.at[nome_de, nome_para] = f"(inv) {setup_inv.tempo_setup}"
                else:
                    matriz.at[nome_de, nome_para] = ""

    # Exporta para Excel em memória
    stream = io.BytesIO()
    matriz.to_excel(stream, engine="openpyxl")
    stream.seek(0)

    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=setup_matrix_model.xlsx"}
    )
