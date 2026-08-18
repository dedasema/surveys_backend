# tests/test_roles_permisos.py
from app.models.catalogos import Rol, Permiso

def test_crear_y_listar_permisos(db_session):
    p1 = Permiso(codigo="test:leer", nombre="Leer Test", modulo="Test", descripcion="Permite leer")
    p2 = Permiso(codigo="test:escribir", nombre="Escribir Test", modulo="Test", descripcion="Permite escribir")
    db_session.add_all([p1, p2])
    db_session.commit()

    permisos = db_session.query(Permiso).filter(Permiso.modulo == "Test").all()
    assert len(permisos) == 2

def test_asignar_permisos_a_rol(db_session):
    p = Permiso(codigo="modulo:accion", nombre="Accion Test", modulo="Modulo", descripcion="Desc")
    rol = Rol(nombre="test_role", descripcion="Rol de testing")
    db_session.add_all([p, rol])
    db_session.commit()

    rol.permisos = [p]
    db_session.commit()

    db_session.refresh(rol)
    assert len(rol.permisos) == 1
    assert rol.permisos[0].codigo == "modulo:accion"
