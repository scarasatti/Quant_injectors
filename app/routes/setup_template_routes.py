from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from fastapi.responses import StreamingResponse
import pandas as pd
import io

from app.database import get_db
from app.models.composition_line import CompositionLine
from app.models.setup import Setup
from sqlalchemy.orm import joinedload

router = APIRouter(prefix="/template", tags=["Templates"])

@router.get("/setup-matrix")
def download_setup_template(db: Session = Depends(get_db)):
    # Buscar todas as composition lines com mold e product carregados
    composition_lines = db.query(CompositionLine).options(
        joinedload(CompositionLine.mold),
        joinedload(CompositionLine.product)
    ).all()
    
    # Criar rótulos no formato "M{id_mold}-{nome_produto}"
    rotulos = []
    id_por_rotulo = {}
    rotulo_por_id = {}
    
    for cl in composition_lines:
        rotulo = f"M{cl.mold_id}-{cl.product.name}"
        rotulos.append(rotulo)
        id_por_rotulo[rotulo] = cl.id
        rotulo_por_id[cl.id] = rotulo
    
    # Cria DataFrame com índice e colunas iguais
    matriz = pd.DataFrame("", index=rotulos, columns=rotulos)
    matriz.index.name = "De\\Para"

    for rotulo_de in rotulos:
        for rotulo_para in rotulos:
            id_de = id_por_rotulo[rotulo_de]
            id_para = id_por_rotulo[rotulo_para]
            
            if id_de == id_para:
                matriz.at[rotulo_de, rotulo_para] = 0
                continue

            setup = db.query(Setup).filter_by(
                from_composition_line_id=id_de,
                to_composition_line_id=id_para
            ).first()

            if setup:
                matriz.at[rotulo_de, rotulo_para] = setup.setup_time
            else:
                # Tenta buscar o inverso, apenas para exibição
                setup_inv = db.query(Setup).filter_by(
                    from_composition_line_id=id_para,
                    to_composition_line_id=id_de
                ).first()
                if setup_inv:
                    matriz.at[rotulo_de, rotulo_para] = f"(inv) {setup_inv.setup_time}"
                else:
                    matriz.at[rotulo_de, rotulo_para] = ""

    # Exporta para Excel em memória
    stream = io.BytesIO()
    matriz.to_excel(stream, engine="openpyxl")
    stream.seek(0)

    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=setup_matrix.xlsx"}
    )
