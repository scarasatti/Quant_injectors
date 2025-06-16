from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
import pandas as pd
from io import BytesIO
import traceback

from app.database import get_db
from app.models.product import Product
from app.models.setup import Setup

router = APIRouter(prefix="/upload")

@router.post("/setup-matrix-xlsx")
def upload_setup_matrix_xlsx(file: UploadFile = File(...), db: Session = Depends(get_db)):
    try:
        contents = file.file.read()
        df = pd.read_excel(BytesIO(contents), index_col=0)

        print("📊 DataFrame carregado:")
        print(df)

        produtos = list(df.columns)
        print(f"🧾 Produtos detectados: {produtos}")

        # Mapeia os nomes para os IDs dos produtos
        produtos_db = db.query(Product).filter(Product.name.in_(produtos)).all()
        nome_para_id = {p.name: p.id for p in produtos_db}

        for i_nome in produtos:
            for j_nome in produtos:
                i_id = nome_para_id.get(i_nome)
                j_id = nome_para_id.get(j_nome)

                if i_id is None or j_id is None:
                    print(f"❌ Produto não encontrado no banco: {i_nome} ou {j_nome}")
                    continue

                tempo_raw = df.loc[i_nome, j_nome]

                if pd.isna(tempo_raw):
                    continue

                try:
                    tempo = int(tempo_raw)
                except ValueError:
                    print(f"⚠️ Tempo inválido para {i_nome} → {j_nome}: {tempo_raw}")
                    continue

                print(f"➡️ {i_nome} → {j_nome} = {tempo}")

                # Cadastra apenas o par explícito da planilha, sem espelhamento
                existe = db.query(Setup).filter(
                    Setup.produto_de == i_id,
                    Setup.produto_para == j_id
                ).first()

                if not existe:
                    db.add(Setup(
                        produto_de=i_id,
                        produto_para=j_id,
                        tempo_setup=tempo
                    ))

        db.commit()
        return {"message": "Setups cadastrados com base na planilha. Apenas os valores explícitos foram processados."}

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Erro ao processar o arquivo: {str(e)}")
