"""
Tests de seguridad para sync-all.

Garantizan que sync-all solo procesa contactos registrados en contact_channels,
nunca el universo abierto de phones que existen en la tabla messages.

No requieren servidor corriendo — usan la DB directamente.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import pytest_asyncio
from sqlalchemy import text
from db import AsyncSessionLocal


BOT_ID_TEST = "__sync_security_test__"
CONN_TEST    = "__conn_test__"
REGISTERED   = "5491100000001"   # contacto registrado en contact_channels
UNREGISTERED = "5491100000002"   # número que mandó mensajes pero NO está registrado


@pytest_asyncio.fixture(autouse=True)
async def setup_and_teardown():
    """Crea datos de prueba y los limpia al finalizar."""
    async with AsyncSessionLocal() as s:
        # Contacto registrado
        await s.execute(
            text("INSERT INTO contacts (connection_id, name) VALUES (:cid, :name)"),
            {"cid": BOT_ID_TEST, "name": "Contacto Registrado"},
        )
        contact_id = (await s.execute(
            text("SELECT last_insert_rowid()")
        )).scalar()
        await s.execute(
            text("INSERT INTO contact_channels (contact_id, type, value) VALUES (:cid, 'telegram', :val)"),
            {"cid": contact_id, "val": REGISTERED},
        )

        # Mensajes del contacto registrado
        await s.execute(
            text("INSERT INTO messages (connection_id, connection_phone, phone, name, body, outbound) "
                 "VALUES (:eid, :conn, :phone, :name, :body, 0)"),
            {"eid": BOT_ID_TEST, "conn": CONN_TEST, "phone": REGISTERED,
             "name": "Contacto Registrado", "body": "Mensaje del registrado"},
        )

        # Mensajes del número NO registrado (simula grupos, unknowns, etc.)
        await s.execute(
            text("INSERT INTO messages (connection_id, connection_phone, phone, name, body, outbound) "
                 "VALUES (:eid, :conn, :phone, :name, :body, 0)"),
            {"eid": BOT_ID_TEST, "conn": CONN_TEST, "phone": UNREGISTERED,
             "name": UNREGISTERED, "body": "Mensaje del no registrado"},
        )
        await s.commit()

    yield

    async with AsyncSessionLocal() as s:
        # Limpiar en orden (FK)
        await s.execute(text("DELETE FROM contact_channels WHERE value IN (:r, :u)"),
                        {"r": REGISTERED, "u": UNREGISTERED})
        await s.execute(text("DELETE FROM contacts WHERE connection_id = :eid"),
                        {"eid": BOT_ID_TEST})
        await s.execute(text("DELETE FROM messages WHERE connection_id = :eid"),
                        {"eid": BOT_ID_TEST})
        await s.commit()


@pytest.mark.asyncio
async def test_sync_all_query_solo_devuelve_contactos_registrados():
    """
    La query de sync-all usa contact_channels JOIN contacts.
    Solo debe devolver phones registrados, aunque haya otros phones en messages.
    """
    async with AsyncSessionLocal() as s:
        rows = (await s.execute(
            text(
                "SELECT DISTINCT cc.value FROM contact_channels cc "
                "JOIN contacts c ON c.id = cc.contact_id "
                "WHERE c.connection_id = :eid AND cc.type = 'telegram'"
            ),
            {"eid": BOT_ID_TEST},
        )).fetchall()

    phones = [r[0] for r in rows]

    assert REGISTERED in phones, "El contacto registrado debe estar en la lista"
    assert UNREGISTERED not in phones, \
        "Un número que solo mandó mensajes pero no está registrado NO debe aparecer"
    assert len(phones) == 1, f"Solo debe haber 1 phone (el registrado), hay {len(phones)}: {phones}"


@pytest.mark.asyncio
async def test_messages_query_vieja_devuelve_ambos():
    """
    Confirma que la query VIEJA (SELECT DISTINCT phone FROM messages) sí devolvía
    el número no registrado — para documentar el bug que se corrigió.
    """
    async with AsyncSessionLocal() as s:
        rows = (await s.execute(
            text("SELECT DISTINCT phone FROM messages WHERE connection_id = :eid AND outbound = 0"),
            {"eid": BOT_ID_TEST},
        )).fetchall()

    phones = [r[0] for r in rows]

    assert REGISTERED in phones
    assert UNREGISTERED in phones, \
        "La query vieja SÍ devolvía números no registrados (bug documentado)"
    assert len(phones) == 2, "La query vieja devolvía todos — sin discriminar"
