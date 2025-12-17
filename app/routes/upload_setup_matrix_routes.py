from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
import pandas as pd
from io import BytesIO
import traceback

from app.database import get_db
from app.models.composition_line import CompositionLine
from app.models.setup import Setup
from sqlalchemy.orm import joinedload

router = APIRouter(prefix="/upload")

@router.post("/setup-matrix-xlsx")
def upload_setup_matrix_xlsx(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    try:
        contents = file.file.read()
        df = pd.read_excel(BytesIO(contents), index_col=0)

        print("DataFrame carregado:")
        print(df)

        rotulos = list(df.columns)
        print(f"Composition lines detectadas: {rotulos}")

        # Mapeia os rótulos (formato "M{id_mold}-{nome_produto}") para os IDs das composition lines
        composition_lines_db = db.query(CompositionLine).options(
            joinedload(CompositionLine.mold),
            joinedload(CompositionLine.product)
        ).all()
        rotulo_para_id = {}
        
        for cl in composition_lines_db:
            rotulo = f"M{cl.mold_id}-{cl.product.name}"
            rotulo_para_id[rotulo] = cl.id

        for i_rotulo in rotulos:
            for j_rotulo in rotulos:
                i_id = rotulo_para_id.get(i_rotulo)
                j_id = rotulo_para_id.get(j_rotulo)

                if i_id is None or j_id is None:
                    print(f"Composition line não encontrada no banco: {i_rotulo} ou {j_rotulo}")
                    continue

                tempo_raw = df.loc[i_rotulo, j_rotulo]

                if pd.isna(tempo_raw):
                    continue

                try:
                    # Remove "(inv)" se existir
                    if isinstance(tempo_raw, str) and tempo_raw.startswith("(inv)"):
                        tempo_raw = tempo_raw.replace("(inv)", "").strip()
                    tempo = int(float(tempo_raw))
                except (ValueError, TypeError):
                    print(f"Tempo inválido para {i_rotulo} → {j_rotulo}: {tempo_raw}")
                    continue

                print(f"{i_rotulo} → {j_rotulo} = {tempo} segundos")

                # Cria ou atualiza o setup direto
                setup = db.query(Setup).filter(
                    Setup.from_composition_line_id == i_id,
                    Setup.to_composition_line_id == j_id
                ).first()

                if setup:
                    setup.setup_time = tempo  # Atualiza
                    print(f"Setup atualizado: {i_rotulo} → {j_rotulo}")
                else:
                    db.add(Setup(
                        from_composition_line_id=i_id,
                        to_composition_line_id=j_id,
                        setup_time=tempo
                    ))
                    print(f"Setup criado: {i_rotulo} → {j_rotulo}")

                # Criar automaticamente o setup inverso (espelho) se não for o mesmo
                # Se M1 → M3 = 60s, então M3 → M1 = 60s automaticamente
                if i_id != j_id:  # Não criar espelho se for o mesmo
                    inverse_setup = db.query(Setup).filter(
                        Setup.from_composition_line_id == j_id,
                        Setup.to_composition_line_id == i_id
                    ).first()

                    if inverse_setup:
                        # Atualiza o inverso também
                        inverse_setup.setup_time = tempo
                        print(f"Setup inverso atualizado: {j_rotulo} → {i_rotulo}")
                    else:
                        # Cria o inverso automaticamente
                        db.add(Setup(
                            from_composition_line_id=j_id,
                            to_composition_line_id=i_id,
                            setup_time=tempo  # Mesmo tempo do setup direto
                        ))
                        print(f"Setup inverso criado automaticamente: {j_rotulo} → {i_rotulo}")

        db.commit()
        return {"message": "Setups cadastrados ou atualizados com sucesso."}

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Erro ao processar o arquivo: {str(e)}")
