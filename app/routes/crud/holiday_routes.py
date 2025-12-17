from typing import List
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.models.holiday import Holiday, HolidayLevel
from app.schemas.holiday_schema import (
    HolidayCreate,
    HolidayResponse,
    HolidayUpdate,
)

try:
    import holidays as holidays_lib
except ImportError:  # pragma: no cover
    holidays_lib = None

router = APIRouter(prefix="/feriados", tags=["Feriados"])


def calculate_easter(year: int) -> date:
    """
    Calcula a data da Páscoa usando o algoritmo de Meeus/Jones/Butcher.
    """
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def get_carnival_dates(year: int) -> dict[date, str]:
    """
    Calcula as datas do Carnaval (Segunda e Terça-feira) baseado na Páscoa.
    Retorna um dicionário com as datas e nomes.
    """
    easter = calculate_easter(year)
    # Terça-feira de Carnaval = 47 dias antes da Páscoa
    tuesday = easter - timedelta(days=47)
    # Segunda-feira de Carnaval = 48 dias antes da Páscoa
    monday = easter - timedelta(days=48)
    
    return {
        monday: "Segunda-feira de Carnaval",
        tuesday: "Terça-feira de Carnaval"
    }


@router.post("", response_model=HolidayResponse)
def create_holiday(holiday: HolidayCreate, db: Session = Depends(get_db)):
    existing = db.query(Holiday).filter(Holiday.date == holiday.date).first()
    if existing:
        raise HTTPException(
            status_code=400, detail="Já existe um feriado cadastrado para essa data"
        )

    db_holiday = Holiday(**holiday.model_dump())
    db.add(db_holiday)
    db.commit()
    db.refresh(db_holiday)
    return db_holiday


@router.get("", response_model=List[HolidayResponse])
def list_holidays(db: Session = Depends(get_db)):
    return db.query(Holiday).all()


@router.get("/{holiday_id}", response_model=HolidayResponse)
def get_holiday(holiday_id: int, db: Session = Depends(get_db)):
    holiday = db.query(Holiday).get(holiday_id)
    if not holiday:
        raise HTTPException(status_code=404, detail="Feriado não encontrado")
    return holiday


@router.put("/{holiday_id}", response_model=HolidayResponse)
def update_holiday(holiday_id: int, holiday: HolidayUpdate, db: Session = Depends(get_db)):
    db_holiday = db.query(Holiday).get(holiday_id)
    if not db_holiday:
        raise HTTPException(status_code=404, detail="Feriado não encontrado")

    if holiday.date and holiday.date != db_holiday.date:
        conflict = db.query(Holiday).filter(Holiday.date == holiday.date).first()
        if conflict:
            raise HTTPException(
                status_code=400,
                detail="Já existe um feriado cadastrado para a nova data",
            )

    update_data = holiday.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_holiday, key, value)

    db.commit()
    db.refresh(db_holiday)
    return db_holiday


@router.delete("/{holiday_id}")
def delete_holiday(holiday_id: int, db: Session = Depends(get_db)):
    holiday = db.query(Holiday).get(holiday_id)
    if not holiday:
        raise HTTPException(status_code=404, detail="Feriado não encontrado")
    db.delete(holiday)
    db.commit()
    return {"message": "Feriado removido com sucesso"}


class SyncHolidaysResponse(BaseModel):
    created: List[HolidayResponse]
    skipped: int
    total_found: int
    message: str


@router.post("/sincronizar-nacionais/{year}", response_model=SyncHolidaysResponse)
def sync_national_holidays(
    year: int, 
    db: Session = Depends(get_db),
    force: bool = Query(default=False, description="Forçar sincronização mesmo se já existir feriado nacional na data")
):
    """
    Sincroniza feriados nacionais do Brasil para um ano específico.
    Verifica se já existe um feriado nacional na data antes de adicionar.
    """
    if holidays_lib is None:
        raise HTTPException(
            status_code=400,
            detail="Instale a biblioteca `holidays` (pip install holidays) para importar feriados nacionais",
        )

    br_holidays = holidays_lib.Brazil(years=year)
    created = []
    skipped = 0
    
    # Adiciona Carnaval (não está na biblioteca holidays)
    carnival_dates = get_carnival_dates(year)
    for carnival_date, carnival_name in carnival_dates.items():
        # Verifica se já existe um feriado nacional nesta data
        existing_national = db.query(Holiday).filter(
            Holiday.date == carnival_date,
            Holiday.level == HolidayLevel.NACIONAL
        ).first()
        
        if existing_national:
            if not force:
                skipped += 1
                continue
            else:
                # Se force=True, atualiza o existente
                existing_national.name = carnival_name
                created.append(existing_national)
                continue
        
        # Verifica se existe qualquer feriado na data (não nacional)
        existing_any = db.query(Holiday).filter(Holiday.date == carnival_date).first()
        if existing_any and not force:
            skipped += 1
            continue
        
        db_holiday = Holiday(
            name=carnival_name,
            date=carnival_date,
            level=HolidayLevel.NACIONAL
        )
        db.add(db_holiday)
        created.append(db_holiday)
    
    for holiday_date, name in sorted(br_holidays.items()):
        # Verifica se já existe um feriado nacional nesta data
        existing_national = db.query(Holiday).filter(
            Holiday.date == holiday_date,
            Holiday.level == HolidayLevel.NACIONAL
        ).first()
        
        if existing_national:
            if not force:
                skipped += 1
                continue
            else:
                # Se force=True, atualiza o existente
                existing_national.name = name
                created.append(existing_national)
                continue
        
        # Verifica se existe qualquer feriado na data (não nacional)
        existing_any = db.query(Holiday).filter(Holiday.date == holiday_date).first()
        if existing_any and not force:
            skipped += 1
            continue
        
        db_holiday = Holiday(
            name=name, 
            date=holiday_date, 
            level=HolidayLevel.NACIONAL
        )
        db.add(db_holiday)
        created.append(db_holiday)

    if created:
        db.commit()
        for entry in created:
            db.refresh(entry)

    # Total inclui feriados da biblioteca + Carnaval (2 dias por ano)
    total_found = len(br_holidays) + len(carnival_dates)
    message = f"Sincronização concluída: {len(created)} feriados adicionados/atualizados, {skipped} já existiam"
    
    return SyncHolidaysResponse(
        created=[HolidayResponse.model_validate(h) for h in created],
        skipped=skipped,
        total_found=total_found,
        message=message
    )


@router.post("/sincronizar-nacionais-range", response_model=SyncHolidaysResponse)
def sync_national_holidays_range(
    start_year: int = Query(..., description="Ano inicial"),
    end_year: int = Query(..., description="Ano final"),
    db: Session = Depends(get_db),
    force: bool = Query(default=False, description="Forçar sincronização mesmo se já existir feriado nacional na data")
):
    """
    Sincroniza feriados nacionais do Brasil para um range de anos.
    Útil para popular múltiplos anos de uma vez.
    """
    if holidays_lib is None:
        raise HTTPException(
            status_code=400,
            detail="Instale a biblioteca `holidays` (pip install holidays) para importar feriados nacionais",
        )

    if start_year > end_year:
        raise HTTPException(
            status_code=400,
            detail="O ano inicial deve ser menor ou igual ao ano final"
        )

    if end_year - start_year > 50:
        raise HTTPException(
            status_code=400,
            detail="O range de anos não pode ser maior que 50 anos"
        )

    years_range = range(start_year, end_year + 1)
    br_holidays = holidays_lib.Brazil(years=years_range)
    
    created = []
    skipped = 0
    
    # Adiciona Carnaval para cada ano (não está na biblioteca holidays)
    for year in years_range:
        carnival_dates = get_carnival_dates(year)
        for carnival_date, carnival_name in carnival_dates.items():
            # Verifica se já existe um feriado nacional nesta data
            existing_national = db.query(Holiday).filter(
                Holiday.date == carnival_date,
                Holiday.level == HolidayLevel.NACIONAL
            ).first()
            
            if existing_national:
                if not force:
                    skipped += 1
                    continue
                else:
                    existing_national.name = carnival_name
                    created.append(existing_national)
                    continue
            
            # Verifica se existe qualquer feriado na data
            existing_any = db.query(Holiday).filter(Holiday.date == carnival_date).first()
            if existing_any and not force:
                skipped += 1
                continue
            
            db_holiday = Holiday(
                name=carnival_name,
                date=carnival_date,
                level=HolidayLevel.NACIONAL
            )
            db.add(db_holiday)
            created.append(db_holiday)
    
    for holiday_date, name in sorted(br_holidays.items()):
        # Verifica se já existe um feriado nacional nesta data
        existing_national = db.query(Holiday).filter(
            Holiday.date == holiday_date,
            Holiday.level == HolidayLevel.NACIONAL
        ).first()
        
        if existing_national:
            if not force:
                skipped += 1
                continue
            else:
                # Se force=True, atualiza o existente
                existing_national.name = name
                created.append(existing_national)
                continue
        
        # Verifica se existe qualquer feriado na data (não nacional)
        existing_any = db.query(Holiday).filter(Holiday.date == holiday_date).first()
        if existing_any and not force:
            skipped += 1
            continue
        
        db_holiday = Holiday(
            name=name, 
            date=holiday_date, 
            level=HolidayLevel.NACIONAL
        )
        db.add(db_holiday)
        created.append(db_holiday)

    if created:
        db.commit()
        for entry in created:
            db.refresh(entry)

    # Total inclui feriados da biblioteca + Carnaval (2 dias por ano para cada ano no range)
    total_carnival_days = len(years_range) * 2
    total_found = len(br_holidays) + total_carnival_days
    message = f"Sincronização concluída para {start_year}-{end_year}: {len(created)} feriados adicionados/atualizados, {skipped} já existiam"
    
    return SyncHolidaysResponse(
        created=[HolidayResponse.model_validate(h) for h in created],
        skipped=skipped,
        total_found=total_found,
        message=message
    )


@router.post("/sincronizar-nacionais-automatico", response_model=SyncHolidaysResponse)
def sync_national_holidays_automatic(
    years_ahead: int = Query(default=5, ge=1, le=20, description="Quantos anos à frente sincronizar"),
    db: Session = Depends(get_db)
):
    """
    Sincroniza automaticamente feriados nacionais do Brasil.
    Por padrão, sincroniza do ano atual até 5 anos à frente.
    Esta função garante que os feriados sejam adicionados apenas uma vez.
    """
    if holidays_lib is None:
        raise HTTPException(
            status_code=400,
            detail="Instale a biblioteca `holidays` (pip install holidays) para importar feriados nacionais",
        )

    from datetime import datetime
    current_year = datetime.now().year
    end_year = current_year + years_ahead
    
    years_range = range(current_year, end_year + 1)
    br_holidays = holidays_lib.Brazil(years=years_range)
    
    created = []
    skipped = 0
    
    # Adiciona Carnaval para cada ano (não está na biblioteca holidays)
    for year in years_range:
        carnival_dates = get_carnival_dates(year)
        for carnival_date, carnival_name in carnival_dates.items():
            # Verifica se já existe um feriado nacional nesta data
            existing_national = db.query(Holiday).filter(
                Holiday.date == carnival_date,
                Holiday.level == HolidayLevel.NACIONAL
            ).first()
            
            if existing_national:
                if not force:
                    skipped += 1
                    continue
                else:
                    # Se force=True, atualiza o existente
                    existing_national.name = carnival_name
                    created.append(existing_national)
                    continue
            
            # Verifica se existe qualquer feriado na data (não nacional)
            existing_any = db.query(Holiday).filter(Holiday.date == carnival_date).first()
            if existing_any and not force:
                skipped += 1
                continue
            
            db_holiday = Holiday(
                name=carnival_name,
                date=carnival_date,
                level=HolidayLevel.NACIONAL
            )
            db.add(db_holiday)
            created.append(db_holiday)
    
    for holiday_date, name in sorted(br_holidays.items()):
        # Verifica se já existe um feriado nacional nesta data
        existing_national = db.query(Holiday).filter(
            Holiday.date == holiday_date,
            Holiday.level == HolidayLevel.NACIONAL
        ).first()
        
        if existing_national:
            skipped += 1
            continue
        
        # Se não existe feriado nacional, adiciona
        db_holiday = Holiday(
            name=name, 
            date=holiday_date, 
            level=HolidayLevel.NACIONAL
        )
        db.add(db_holiday)
        created.append(db_holiday)

    if created:
        db.commit()
        for entry in created:
            db.refresh(entry)

    # Total inclui feriados da biblioteca + Carnaval (2 dias por ano para cada ano no range)
    total_carnival_days = len(years_range) * 2
    total_found = len(br_holidays) + total_carnival_days
    message = f"Sincronização automática concluída ({current_year}-{end_year}): {len(created)} feriados adicionados, {skipped} já existiam"
    
    return SyncHolidaysResponse(
        created=[HolidayResponse.model_validate(h) for h in created],
        skipped=skipped,
        total_found=total_found,
        message=message
    )











