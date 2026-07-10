"""Tests unitarios para SaveAttachmentNode."""
import tempfile
from pathlib import Path

import pytest

from .save_attachment import SaveAttachmentNode
from .state import FlowState


def _state(**kwargs) -> FlowState:
    defaults = dict(message="hola", bot_id="bot1", contact_phone="user1", contact_name="Juan", canal="telegram")
    defaults.update(kwargs)
    return FlowState(**defaults)


@pytest.mark.asyncio
async def test_mueve_archivo_real(tmp_path):
    src = tmp_path / "audio.ogg"
    src.write_text("contenido")
    node = SaveAttachmentNode({})
    state = _state(attachment_path=str(src))
    result = await node.run(state)
    assert result.attachment_path != str(src)
    assert Path(result.attachment_path).exists()
    assert not src.exists()


@pytest.mark.asyncio
async def test_sim_no_mueve_archivo(tmp_path, caplog):
    """En simulación (_sim=True): el archivo se queda donde está, no se mueve."""
    src = tmp_path / "audio.ogg"
    src.write_text("contenido")
    node = SaveAttachmentNode({})
    state = _state(attachment_path=str(src))
    state.data["_sim"] = True
    with caplog.at_level("INFO"):
        result = await node.run(state)
    assert result.attachment_path == str(src)
    assert src.exists()
    assert any("[sim]" in r.message for r in caplog.records)
