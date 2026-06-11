"""
Tests del dedup persistente del poller wavi (tabla wavi_seen).

Usan la DB del worktree con claves únicas por corrida y limpian al final.
No requieren server corriendo (acceden a db.py directo).
"""
import sys
import uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import pytest_asyncio

import db


@pytest_asyncio.fixture
async def test_session_name():
    """Nombre único por test + cleanup de sus filas en wavi_seen."""
    name = f"_test_dedup_{uuid.uuid4().hex[:8]}"
    await db.init_db()  # asegura que la tabla exista aunque el server no haya corrido
    yield name
    async with db.AsyncSessionLocal() as session:
        await session.execute(
            db.text("DELETE FROM wavi_seen WHERE session = :s"), {"s": name}
        )
        await session.commit()


def test_wavi_msg_hash_deterministico():
    assert db.wavi_msg_hash("hola") == db.wavi_msg_hash("hola")
    assert db.wavi_msg_hash("hola") != db.wavi_msg_hash("chau")
    assert len(db.wavi_msg_hash("hola")) == 16


@pytest.mark.asyncio
async def test_seen_add_y_has(test_session_name):
    h = db.wavi_msg_hash("mensaje de prueba")
    assert not await db.wavi_seen_has(test_session_name, "Contacto", h)
    await db.wavi_seen_add(test_session_name, "Contacto", h)
    assert await db.wavi_seen_has(test_session_name, "Contacto", h)


@pytest.mark.asyncio
async def test_seen_add_idempotente(test_session_name):
    h = db.wavi_msg_hash("repetido")
    await db.wavi_seen_add(test_session_name, "Contacto", h)
    await db.wavi_seen_add(test_session_name, "Contacto", h)  # INSERT OR IGNORE: no explota
    assert await db.wavi_seen_has(test_session_name, "Contacto", h)


@pytest.mark.asyncio
async def test_seen_separa_contactos_y_sesiones(test_session_name):
    h = db.wavi_msg_hash("mismo texto")
    await db.wavi_seen_add(test_session_name, "Contacto A", h)
    assert not await db.wavi_seen_has(test_session_name, "Contacto B", h)
    assert not await db.wavi_seen_has(test_session_name + "_otra", "Contacto A", h)


@pytest.mark.asyncio
async def test_prune_borra_solo_viejas(test_session_name):
    h = db.wavi_msg_hash("reciente")
    await db.wavi_seen_add(test_session_name, "Contacto", h)
    # Insertar una entrada vieja a mano (20 días atrás)
    async with db.AsyncSessionLocal() as session:
        await session.execute(
            db.text("""
                INSERT OR IGNORE INTO wavi_seen (session, contact, msg_hash, created_at)
                VALUES (:s, :c, :h, datetime('now', '-20 days'))
            """),
            {"s": test_session_name, "c": "Contacto", "h": db.wavi_msg_hash("viejo")},
        )
        await session.commit()

    pruned = await db.wavi_seen_prune(days=14)
    assert pruned >= 1
    assert await db.wavi_seen_has(test_session_name, "Contacto", h), "la reciente sobrevive"
    assert not await db.wavi_seen_has(test_session_name, "Contacto", db.wavi_msg_hash("viejo"))
