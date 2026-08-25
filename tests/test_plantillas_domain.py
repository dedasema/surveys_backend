"""
Unit tests for Plantilla, Pregunta, and Opcion Domain Entities.
Tests invariants and aggregate operations in memory without any DB dependency.
"""

from uuid import uuid4
import pytest

from app.modules.plantillas.domain.entities import Plantilla, Pregunta, Opcion
from app.modules.plantillas.domain.exceptions import PlantillaDomainError


def test_create_plantilla_success():
    suscriptor_id = uuid4()
    plantilla = Plantilla(
        suscriptor_id=suscriptor_id,
        nombre="Encuesta Clientes 2026",
        descripcion="Feedback de calidad",
    )
    assert plantilla.nombre == "Encuesta Clientes 2026"
    assert plantilla.descripcion == "Feedback de calidad"
    assert len(plantilla.preguntas) == 0


def test_cannot_create_plantilla_with_blank_name():
    with pytest.raises(PlantillaDomainError, match="no puede estar vacío"):
        Plantilla(suscriptor_id=uuid4(), nombre="   ")


def test_agregar_preguntas_y_opciones_aggregate():
    plantilla = Plantilla(suscriptor_id=uuid4(), nombre="Encuesta NPS")
    
    # 1. Agregar pregunta
    p1 = plantilla.agregar_pregunta(
        texto="¿Qué tan probable es que nos recomiendes?",
        tipo_pregunta_id=5,  # NPS
        obligatorio=True,
    )
    assert len(plantilla.preguntas) == 1
    assert p1.orden == 1
    assert p1.plantilla_id == plantilla.id

    # 2. Agregar opciones
    op1 = p1.agregar_opcion(texto="Muy probable", valor="10")
    op2 = p1.agregar_opcion(texto="Poco probable", valor="1")
    assert len(p1.opciones) == 2
    assert op1.texto == "Muy probable"
    assert op2.valor == "1"


def test_cannot_add_pregunta_with_invalid_type():
    with pytest.raises(PlantillaDomainError, match="tipo_pregunta_id"):
        Pregunta(
            id=uuid4(),
            plantilla_id=uuid4(),
            texto="Pregunta inválida",
            tipo_pregunta_id=0,
        )
