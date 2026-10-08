"""Endpoints REST para el Catálogo de Radios y Antenas."""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from backend.app.core.database import get_session
from backend.app.models.radio import Radio, RadioBase
from backend.app.models.antenna import Antenna, AntennaBase

router = APIRouter()


# --- RADIOS ---

@router.get("/radios", response_model=List[Radio], summary="Obtener todos los radios")
def list_radios(session: Session = Depends(get_session)):
    statement = select(Radio).order_by(Radio.manufacturer.asc(), Radio.model.asc())
    return session.exec(statement).all()


@router.get("/radios/{radio_id}", response_model=Radio, summary="Obtener radio por ID")
def get_radio(radio_id: int, session: Session = Depends(get_session)):
    radio = session.get(Radio, radio_id)
    if not radio:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Radio no encontrado")
    return radio


@router.post("/radios", response_model=Radio, status_code=status.HTTP_201_CREATED, summary="Crear nuevo radio")
def create_radio(radio_in: RadioBase, session: Session = Depends(get_session)):
    # Verificar si el modelo ya existe
    existing = session.exec(select(Radio).where(Radio.model == radio_in.model)).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El modelo de radio ya existe")

    db_radio = Radio.model_validate(radio_in)
    session.add(db_radio)
    session.commit()
    session.refresh(db_radio)
    return db_radio


# --- ANTENAS ---

@router.get("/antennas", response_model=List[Antenna], summary="Obtener todas las antenas")
def list_antennas(session: Session = Depends(get_session)):
    statement = select(Antenna).order_by(Antenna.manufacturer.asc(), Antenna.model.asc())
    return session.exec(statement).all()


@router.get("/antennas/{antenna_id}", response_model=Antenna, summary="Obtener antena por ID")
def get_antenna(antenna_id: int, session: Session = Depends(get_session)):
    antenna = session.get(Antenna, antenna_id)
    if not antenna:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Antena no encontrada")
    return antenna


@router.post("/antennas", response_model=Antenna, status_code=status.HTTP_201_CREATED, summary="Crear nueva antena")
def create_antenna(antenna_in: AntennaBase, session: Session = Depends(get_session)):
    existing = session.exec(select(Antenna).where(Antenna.model == antenna_in.model)).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El modelo de antena ya existe")

    db_antenna = Antenna.model_validate(antenna_in)
    session.add(db_antenna)
    session.commit()
    session.refresh(db_antenna)
    return db_antenna
