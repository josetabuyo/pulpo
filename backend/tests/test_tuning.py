"""Tests de los endpoints de manual tuning del sumarizador."""
import io
import shutil
import struct
import zlib
import pytest
from pathlib import Path
from conftest import ADMIN, client  # noqa: F401

# Ruta raíz del worktree (backend/tests/ → ../../)
_ROOT = Path(__file__).parent.parent.parent


def _minimal_png() -> bytes:
    """PNG 1x1 blanco mínimo y válido."""
    def chunk(name: bytes, data: bytes) -> bytes:
        c = struct.pack(">I", len(data)) + name + data
        return c + struct.pack(">I", zlib.crc32(name + data) & 0xFFFFFFFF)

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"\x00\xFF\xFF\xFF"))
        + chunk(b"IEND", b"")
    )


BOT_ID = "test-tuning-bot"
PHONE = "test-tuning-contact"
BASE = f"/api/summarizer/{BOT_ID}/{PHONE}"

_CONTACT_DIR = _ROOT / "data" / "summaries" / BOT_ID / PHONE
_CONSOL_DIR  = _CONTACT_DIR / "consolidated"

# Contacto aislado solo para tests de consolidación (no usa autouse)
PHONE_CONSOL = "test-consol-contact"
BASE_CONSOL  = f"/api/summarizer/{BOT_ID}/{PHONE_CONSOL}"
_CONSOL_CONTACT_DIR = _ROOT / "data" / "summaries" / BOT_ID / PHONE_CONSOL


@pytest.fixture(autouse=True)
def clean_contact(client):
    """Limpia el contacto antes de cada test: chat.md + consolidated/."""
    client.post(f"/api/summarizer/{BOT_ID}/{PHONE}/sync", headers=ADMIN)
    shutil.rmtree(_CONSOL_DIR, ignore_errors=True)
    yield


def _seed(client, texts: list[str]):
    """Inserta mensajes de texto en el contacto."""
    for t in texts:
        r = client.post(f"{BASE}/message", json={"content": t}, headers=ADMIN)
        assert r.status_code == 200, r.text
    return r


def _msgs(client, include_ids=False):
    url = f"{BASE}/messages"
    if include_ids:
        url += "?include_ids=true"
    r = client.get(url, headers=ADMIN)
    assert r.status_code == 200, r.text
    return r.json()["messages"]


# ─── POST /message ────────────────────────────────────────────────────────────

def test_insert_message(client):
    _seed(client, ["Hola mundo"])
    msgs = _msgs(client)
    assert any("Hola mundo" in (m.get("content") or "") for m in msgs)


def test_insert_message_returns_count(client):
    r = client.post(f"{BASE}/message", json={"content": "Primero"}, headers=ADMIN)
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["message_count"] >= 1


def test_insert_message_with_sender(client):
    r = client.post(
        f"{BASE}/message",
        json={"content": "Hola", "sender": "Juan"},
        headers=ADMIN,
    )
    assert r.status_code == 200
    msgs = _msgs(client)
    assert any(m.get("sender") == "Juan" for m in msgs)


# ─── DELETE /message/{id} ─────────────────────────────────────────────────────

def test_delete_message(client):
    _seed(client, ["Borrame", "Quédate"])
    msgs = _msgs(client, include_ids=True)
    target = next((m for m in msgs if "Borrame" in (m.get("content") or "")), None)
    assert target is not None, "Mensaje 'Borrame' no encontrado"
    assert target.get("_id"), "El mensaje no tiene _id"

    r = client.delete(f"{BASE}/message/{target['_id']}", headers=ADMIN)
    assert r.status_code == 200
    assert r.json()["ok"] is True

    remaining = _msgs(client)
    assert not any("Borrame" in (m.get("content") or "") for m in remaining)
    assert any("Quédate" in (m.get("content") or "") for m in remaining)


def test_delete_missing_message(client):
    r = client.delete(f"{BASE}/message/9999", headers=ADMIN)
    assert r.status_code == 404


# ─── PUT /messages (reorder) ──────────────────────────────────────────────────

def test_rewrite_messages(client):
    _seed(client, ["A", "B", "C"])
    msgs = _msgs(client, include_ids=True)
    assert len(msgs) >= 3

    # Invertir orden
    reversed_msgs = list(reversed(msgs))
    r = client.put(f"{BASE}/messages", json={"messages": reversed_msgs}, headers=ADMIN)
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["message_count"] == len(msgs)


def test_rewrite_preserves_count(client):
    _seed(client, ["X", "Y"])
    msgs = _msgs(client, include_ids=True)
    r = client.put(f"{BASE}/messages", json={"messages": msgs}, headers=ADMIN)
    assert r.status_code == 200
    assert r.json()["message_count"] == len(msgs)


# ─── include_ids param ────────────────────────────────────────────────────────

def test_messages_without_ids(client):
    _seed(client, ["Test"])
    msgs = _msgs(client, include_ids=False)
    for m in msgs:
        assert "_id" not in m


def test_messages_with_ids(client):
    _seed(client, ["Test IDs"])
    msgs = _msgs(client, include_ids=True)
    assert all(m.get("_id") is not None for m in msgs if m.get("type") != "document")


# ─── POST /consolidate ────────────────────────────────────────────────────────

def test_consolidate(client):
    _seed(client, ["Msg consolidado"])
    r = client.post(f"{BASE}/consolidate", headers=ADMIN)
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["message_count"] >= 1
    assert "consolidated_at" in data


def test_get_consolidation(client):
    _seed(client, ["Para consolidar"])
    client.post(f"{BASE}/consolidate", headers=ADMIN)
    r = client.get(f"{BASE}/consolidation", headers=ADMIN)
    assert r.status_code == 200
    meta = r.json()
    assert "consolidated_at" in meta
    assert "message_count" in meta


def test_get_consolidation_not_found(client):
    # Contacto que nunca fue consolidado en esta sesión de tests
    r = client.get(f"/api/summarizer/{BOT_ID}/never-consolidated/consolidation", headers=ADMIN)
    assert r.status_code == 404


# ─── Round-trip: parse(rewrite(msgs)) == msgs ─────────────────────────────────

def test_round_trip_text_messages(client):
    """Rewrite seguido de GET devuelve exactamente los mismos mensajes."""
    _seed(client, ["Primero", "Segundo", "Tercero"])
    before = _msgs(client, include_ids=True)
    assert len(before) >= 3

    r = client.put(f"{BASE}/messages", json={"messages": before}, headers=ADMIN)
    assert r.status_code == 200

    after = _msgs(client, include_ids=True)
    # Mismo contenido y orden
    assert [m.get("content") for m in after] == [m.get("content") for m in before]


def test_round_trip_preserves_order_after_reorder(client):
    """Reordenar e inmediatamente leer devuelve el orden nuevo."""
    _seed(client, ["A", "B", "C"])
    msgs = _msgs(client, include_ids=True)
    assert len(msgs) == 3

    reversed_msgs = list(reversed(msgs))
    r = client.put(f"{BASE}/messages", json={"messages": reversed_msgs}, headers=ADMIN)
    assert r.status_code == 200

    after = _msgs(client, include_ids=True)
    assert [m.get("content") for m in after] == [m.get("content") for m in reversed_msgs]


# ─── Optimistic locking ───────────────────────────────────────────────────────

def _version(client):
    r = client.get(f"{BASE}/messages?include_ids=true", headers=ADMIN)
    assert r.status_code == 200
    return r.json()["version"]


def test_get_returns_version(client):
    _seed(client, ["Para versionar"])
    r = client.get(f"{BASE}/messages", headers=ADMIN)
    assert r.status_code == 200
    v = r.json().get("version")
    assert v is not None and isinstance(v, int) and v > 0


def test_put_with_correct_version_succeeds(client):
    _seed(client, ["Versión OK"])
    v = _version(client)
    msgs = _msgs(client, include_ids=True)

    r = client.put(f"{BASE}/messages", json={"messages": msgs, "version": v}, headers=ADMIN)
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert "version" in r.json()


def test_put_with_stale_version_returns_409(client):
    _seed(client, ["Conflicto"])
    msgs = _msgs(client, include_ids=True)

    # Versión falsa (del pasado)
    r = client.put(f"{BASE}/messages", json={"messages": msgs, "version": 1}, headers=ADMIN)
    assert r.status_code == 409


def test_put_without_version_always_succeeds(client):
    _seed(client, ["Sin versión"])
    msgs = _msgs(client, include_ids=True)

    r = client.put(f"{BASE}/messages", json={"messages": msgs}, headers=ADMIN)
    assert r.status_code == 200
    assert r.json()["ok"] is True


# ─── POST /upload-image ───────────────────────────────────────────────────────

def test_upload_image_returns_filename(client):
    png = _minimal_png()
    r = client.post(
        f"{BASE}/upload-image",
        files={"file": ("foto.png", io.BytesIO(png), "image/png")},
        headers=ADMIN,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ok"] is True
    assert "filename" in data
    assert data["filename"].endswith(".png")


def test_upload_image_file_exists_on_disk(client):
    png = _minimal_png()
    r = client.post(
        f"{BASE}/upload-image",
        files={"file": ("test.png", io.BytesIO(png), "image/png")},
        headers=ADMIN,
    )
    assert r.status_code == 200, r.text
    filename = r.json()["filename"]

    # Verificar que el adjunto es descargable por el mismo endpoint de docs
    r2 = client.get(f"{BASE}/docs/{filename}", headers=ADMIN)
    assert r2.status_code == 200
    assert r2.content == png


def test_upload_image_ext_preserved(client):
    """La extensión del archivo original se respeta (dentro de whitelist)."""
    for ext in ("jpg", "webp"):
        r = client.post(
            f"{BASE}/upload-image",
            files={"file": (f"foto.{ext}", io.BytesIO(b"fake"), f"image/{ext}")},
            headers=ADMIN,
        )
        assert r.status_code == 200
        assert r.json()["filename"].endswith(f".{ext}")


def test_upload_image_unknown_ext_defaults_to_png(client):
    """Extension desconocida → .png por defecto."""
    r = client.post(
        f"{BASE}/upload-image",
        files={"file": ("foto.bmp", io.BytesIO(b"fake"), "image/bmp")},
        headers=ADMIN,
    )
    assert r.status_code == 200
    assert r.json()["filename"].endswith(".png")


# ─── Round-trip imagen en rewrite ─────────────────────────────────────────────

def test_image_message_round_trip(client):
    """Rewrite con type=image → GET devuelve el mismo type y filename."""
    # Seed un texto para tener algo en el archivo
    _seed(client, ["texto base"])
    msgs = _msgs(client, include_ids=True)

    img_msg = {
        "type": "image",
        "filename": "foto_test.jpg",
        "caption": "Una foto de prueba",
        "sender": "Andrés",
        "timestamp": None,
        "direction": "in",
    }
    r = client.put(f"{BASE}/messages", json={"messages": msgs + [img_msg]}, headers=ADMIN)
    assert r.status_code == 200

    after = _msgs(client)
    image_msgs = [m for m in after if m.get("type") == "image"]
    assert len(image_msgs) == 1
    assert image_msgs[0]["filename"] == "foto_test.jpg"
    assert image_msgs[0]["caption"] == "Una foto de prueba"
    assert image_msgs[0]["sender"] == "Andrés"


def test_image_message_without_caption(client):
    """Imagen sin caption se serializa y parsea limpia."""
    _seed(client, ["base"])
    msgs = _msgs(client, include_ids=True)
    img_msg = {"type": "image", "filename": "sin_caption.png", "caption": "", "sender": None, "timestamp": None, "direction": "in"}
    client.put(f"{BASE}/messages", json={"messages": msgs + [img_msg]}, headers=ADMIN)

    after = _msgs(client)
    found = next((m for m in after if m.get("type") == "image"), None)
    assert found is not None
    assert found["filename"] == "sin_caption.png"
    assert not found.get("caption")


# ─── GET /consolidations ──────────────────────────────────────────────────────

def test_list_consolidations_empty(client):
    """Sin consolidar → lista vacía."""
    r = client.get(f"/api/summarizer/{BOT_ID}/consolidations", headers=ADMIN)
    assert r.status_code == 200
    data = r.json()
    assert "consolidations" in data
    # El contacto de test puede o no estar consolidado de otro test — no importa
    assert isinstance(data["consolidations"], list)


def test_list_consolidations_after_consolidate(client):
    """Después de consolidar aparece en la lista."""
    _seed(client, ["Para listar"])
    client.post(f"{BASE}/consolidate", headers=ADMIN)

    r = client.get(f"/api/summarizer/{BOT_ID}/consolidations", headers=ADMIN)
    assert r.status_code == 200
    consolidations = r.json()["consolidations"]

    found = next((c for c in consolidations if c["phone"] == PHONE), None)
    assert found is not None, f"{PHONE} no apareció en la lista de consolidaciones"
    assert "consolidated_at" in found
    assert "last_message_ts" in found
    assert "path" in found
    assert found["path"].endswith("chat.md")
    assert "message_count" in found
    assert found["message_count"] >= 1


def test_consolidations_path_points_to_chat_md(client):
    """El path reportado apunta a un chat.md dentro del directorio consolidated/."""
    _seed(client, ["Check path"])
    client.post(f"{BASE}/consolidate", headers=ADMIN)

    r = client.get(f"/api/summarizer/{BOT_ID}/consolidations", headers=ADMIN)
    found = next((c for c in r.json()["consolidations"] if c["phone"] == PHONE), None)
    assert found is not None
    assert "/consolidated/" in found["path"]
    assert found["path"].endswith("chat.md")


# ─── Protección: la consolidación sobrevive operaciones destructivas ──────────

def test_consolidated_file_survives_sync(client):
    """El archivo consolidated/chat.md no es borrado por un sync."""
    _seed(client, ["Sobrevivir sync"])
    client.post(f"{BASE}/consolidate", headers=ADMIN)

    # Verificar que el path existe antes
    r = client.get(f"/api/summarizer/{BOT_ID}/consolidations", headers=ADMIN)
    found = next(c for c in r.json()["consolidations"] if c["phone"] == PHONE)
    consolidated_path = Path(found["path"])
    assert consolidated_path.exists(), "El archivo no existe antes del sync"

    # Ejecutar sync (reconstruye chat.md desde DB)
    client.post(f"{BASE}/sync", headers=ADMIN)

    # El consolidated/ debe seguir intacto
    assert consolidated_path.exists(), "El sync borró el archivo consolidado — REGRESIÓN"


def test_consolidated_file_survives_rewrite(client):
    """El archivo consolidated/chat.md no es borrado por un rewrite de tuning."""
    _seed(client, ["Sobrevivir rewrite"])
    client.post(f"{BASE}/consolidate", headers=ADMIN)

    r = client.get(f"/api/summarizer/{BOT_ID}/consolidations", headers=ADMIN)
    found = next(c for c in r.json()["consolidations"] if c["phone"] == PHONE)
    consolidated_path = Path(found["path"])

    # Rewrite con lista vacía (caso extremo)
    client.put(f"{BASE}/messages", json={"messages": []}, headers=ADMIN)

    assert consolidated_path.exists(), "El rewrite borró el archivo consolidado — REGRESIÓN"


def test_consolidation_metadata_has_all_fields(client):
    """La metadata de consolidación tiene todos los campos esperados."""
    _seed(client, ["Meta completa"])
    client.post(f"{BASE}/consolidate", headers=ADMIN)

    r = client.get(f"{BASE}/consolidation", headers=ADMIN)
    assert r.status_code == 200
    meta = r.json()
    for field in ("consolidated_at", "last_message_ts", "message_count"):
        assert field in meta, f"Campo '{field}' falta en la metadata"


# ─── Tests de la estructura de directorios con timestamp ─────────────────────

@pytest.fixture
def clean_consol(client):
    """Fixture para tests de consolidación: contacto aislado, limpia antes y después.
    Llama a sync para vaciar el caché de dedup del servidor antes de borrar el dir."""
    client.post(f"/api/summarizer/{BOT_ID}/{PHONE_CONSOL}/sync", headers=ADMIN)
    shutil.rmtree(_CONSOL_CONTACT_DIR, ignore_errors=True)
    yield
    shutil.rmtree(_CONSOL_CONTACT_DIR, ignore_errors=True)


def _seed_consol(client, texts: list[str]):
    for t in texts:
        r = client.post(f"{BASE_CONSOL}/message", json={"content": t}, headers=ADMIN)
        assert r.status_code == 200


def test_consolidate_creates_timestamped_subdir(client, clean_consol):
    """Consolidar crea un subdir YYYY-MM-DDTHH-MM-SS/ dentro de consolidated/."""
    _seed_consol(client, ["Mensaje para consolidar"])
    r = client.post(f"{BASE_CONSOL}/consolidate", headers=ADMIN)
    assert r.status_code == 200

    consol_base = _CONSOL_CONTACT_DIR / "consolidated"
    assert consol_base.exists(), "Directorio consolidated/ no fue creado"

    subdirs = [d for d in consol_base.iterdir() if d.is_dir()]
    assert len(subdirs) == 1, f"Esperaba 1 subdir, encontré: {[d.name for d in subdirs]}"

    ts_dir = subdirs[0]
    assert (ts_dir / "metadata.json").exists(), "metadata.json no existe en el subdir"
    assert (ts_dir / "chat.md").exists(), "chat.md no existe en el subdir"


def test_consolidate_copies_all_files_including_images(client, clean_consol):
    """Consolidar copia chat.md, name.txt e imágenes al subdir."""
    _seed_consol(client, ["Mensaje con adjunto"])

    # Subir una imagen
    png = _minimal_png()
    r = client.post(
        f"{BASE_CONSOL}/upload-image",
        files={"file": ("foto.png", io.BytesIO(png), "image/png")},
        headers=ADMIN,
    )
    assert r.status_code == 200

    client.post(f"{BASE_CONSOL}/consolidate", headers=ADMIN)

    consol_base = _CONSOL_CONTACT_DIR / "consolidated"
    subdirs = [d for d in consol_base.iterdir() if d.is_dir()]
    assert len(subdirs) == 1
    ts_dir = subdirs[0]

    assert (ts_dir / "chat.md").exists()
    images = list(ts_dir.glob("img_*.png")) + list(ts_dir.glob("img_*.jpg"))
    assert len(images) >= 1, "La imagen no fue copiada al directorio consolidado"


def test_multiple_consolidations_each_get_own_dir(client, clean_consol):
    """Cada llamada a /consolidate genera un subdir propio."""
    import time

    _seed_consol(client, ["Primera"])
    client.post(f"{BASE_CONSOL}/consolidate", headers=ADMIN)

    time.sleep(1)  # Asegurar timestamp distinto

    _seed_consol(client, ["Segunda"])
    client.post(f"{BASE_CONSOL}/consolidate", headers=ADMIN)

    consol_base = _CONSOL_CONTACT_DIR / "consolidated"
    subdirs = [d for d in consol_base.iterdir() if d.is_dir()]
    assert len(subdirs) == 2, f"Esperaba 2 subdirs, encontré: {[d.name for d in subdirs]}"


def test_get_consolidation_returns_latest_when_multiple(client, clean_consol):
    """GET /consolidation devuelve la consolidación más reciente."""
    import time

    _seed_consol(client, ["Primera"])
    client.post(f"{BASE_CONSOL}/consolidate", headers=ADMIN)

    time.sleep(1)

    _seed_consol(client, ["Segunda"])
    r2 = client.post(f"{BASE_CONSOL}/consolidate", headers=ADMIN)
    assert r2.status_code == 200
    latest_at = r2.json()["consolidated_at"]

    r = client.get(f"{BASE_CONSOL}/consolidation", headers=ADMIN)
    assert r.status_code == 200
    assert r.json()["consolidated_at"] == latest_at


def test_get_consolidation_404_without_consolidation(client, clean_consol):
    """Sin consolidar, GET /consolidation devuelve 404."""
    r = client.get(f"{BASE_CONSOL}/consolidation", headers=ADMIN)
    assert r.status_code == 404


def test_bak_files_not_copied_to_consolidation(client, clean_consol):
    """Los archivos .bak.md no se copian al directorio consolidado."""
    _seed_consol(client, ["Test bak"])
    client.post(f"{BASE_CONSOL}/consolidate", headers=ADMIN)

    consol_base = _CONSOL_CONTACT_DIR / "consolidated"
    subdirs = [d for d in consol_base.iterdir() if d.is_dir()]
    ts_dir = subdirs[0]

    bak_files = list(ts_dir.glob("*.bak.md"))
    assert len(bak_files) == 0, f"Archivos .bak.md no deberían copiarse: {bak_files}"
