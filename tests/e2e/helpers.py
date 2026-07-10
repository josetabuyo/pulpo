"""
Helpers e2e reutilizables para probar flows reales vía Telegram (teli/Telethon)
y flows simulados in-band contra el backend local (simulate_flow, ver
pulpo/business/flows.py y management/HANDOFF_SIMULACION_V2.md).

Convención de carpetas: tests/e2e/<bot>/test_<flow_slug>.py.
`TeliConversation` → marca pytest.mark.e2e (Telegram real, lento, solo antes de
merge). `SimConversation` → marca pytest.mark.e2e_sim (motor real de flows,
sin Telegram, requiere solo el backend local corriendo — ver ADR-004).
No reemplaza tests/test_e2e_luganense_teli.py (flow viejo, referencia intacta) —
esa suite queda tal cual; los flows nuevos usan esta infraestructura.
"""
import asyncio
import re
import time
from pathlib import Path

import httpx

_TELI_DATA = Path("/Users/josetabuyo/Development/teli/data")
_SESSION = str(_TELI_DATA / "sessions" / "user_me")
_API_ID = 31604778
_API_HASH = "385bf75876904b022cb411c1c1954088"


class TeliConversation:
    """
    Conversación multi-turno contra un bot real de Telegram usando la cuenta
    personal del usuario (Telethon). A diferencia del helper de un solo turno
    de test_e2e_luganense_teli.py, mantiene el client abierto entre sends para
    soportar escenarios con varios mensajes seguidos (aclaración, dirección).
    """

    def __init__(self, bot_username: str):
        self._bot_username = bot_username
        self._client = None
        self._bot_entity = None
        self._bot_id = None

    async def __aenter__(self) -> "TeliConversation":
        from telethon import TelegramClient

        self._client = TelegramClient(_SESSION, _API_ID, _API_HASH)
        await self._client.start()
        self._bot_entity = await self._client.get_entity(self._bot_username)
        self._bot_id = self._bot_entity.id
        return self

    async def __aexit__(self, *exc) -> None:
        if self._client:
            await self._client.disconnect()

    async def send_and_wait(self, message: str, timeout: int = 180, settle: int = 15) -> str | None:
        """Envía `message` y devuelve el ÚLTIMO reply del bot (estrategia settle-time)."""
        replies = await self.send_and_collect(message, timeout=timeout, settle=settle)
        return replies[-1] if replies else None

    async def send_and_collect(self, message: str, timeout: int = 180, settle: int = 15) -> list[str]:
        """Envía `message` y devuelve TODOS los replies del bot dentro del timeout."""
        sent = await self._client.send_message(self._bot_username, message)
        last_seen_id = sent.id
        collected: list[str] = []
        first_reply_at: float | None = None
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            await asyncio.sleep(5)
            new_msgs = await self._client.get_messages(self._bot_entity, limit=30, min_id=last_seen_id)
            fresh = [
                m for m in sorted(new_msgs, key=lambda m: m.id)
                if m.sender_id == self._bot_id and m.text
            ]
            for m in fresh:
                collected.append(m.text)
                last_seen_id = m.id
            if collected and first_reply_at is None:
                first_reply_at = time.monotonic()
            if first_reply_at is not None and (time.monotonic() - first_reply_at) >= settle:
                break

        return collected


_UNRESOLVED_TEMPLATE_RE = re.compile(r"\{\{.*?\}\}")


def has_unresolved_templates(*texts: str | None) -> bool:
    """
    True si algún texto contiene un placeholder `{{...}}` sin interpolar
    (ej. el bug real `'{{}}'` de node_1783641146270 en el flow de Luganense,
    ver docs/adr y CLAUDE.md). Ignora None/strings vacíos.
    """
    return any(t and _UNRESOLVED_TEMPLATE_RE.search(t) for t in texts)


class SimConversation:
    """
    Conversación multi-turno contra el motor real de flows, sin Telegram, vía
    el endpoint de simulación in-band `POST /api/flows/bots/{bot_id}/simulate`
    (pulpo/business/flows.py::simulate_message). Equivalente a mandarle el
    mensaje a la bot por Telegram: el flow y el trigger que aplican se
    resuelven solos (igual que dispatch_message), sin flow_id ni
    trigger_node_id. Namespacea la conversación con un `sim_id` reusado entre
    turnos — el mismo mecanismo que permite continuar una simulación pausada
    en `wait_user`.

    A diferencia de `TeliConversation`, no hay settle-time de verdad: el
    motor corre síncrono dentro del propio request HTTP. `settle_seconds`
    es solo un delay chico para no disparar turnos instantáneos pegados.

    Limitación documentada (ver simulate_message.__doc__): solo replica la
    continuación multi-turno vía `wait_user`, no `open_conversation` sin
    wait_user ni el lock `_IN_FLIGHT` de dispatch_message.
    """

    def __init__(self, bot_id: str, base_url: str = "http://localhost:8000"):
        self.bot_id = bot_id
        self.base_url = base_url.rstrip("/")
        self.sim_id: str | None = None
        self.last_run_id: str | None = None
        self._last_steps: list[dict] = []
        # Acumulado de TODOS los steps de TODOS los turnos de la conversación
        # (cada turno de wait_user genera un run_id nuevo — _last_steps solo
        # tiene el último). Necesario para validar cosas que pasaron en un
        # turno anterior (ej. que buscar_directorio corrió bien en el primer
        # turno, aunque el cierre sea 3 turnos después).
        self.all_steps: list[dict] = []
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "SimConversation":
        self._client = httpx.AsyncClient(timeout=300)
        return self

    async def __aexit__(self, *exc) -> None:
        if self._client:
            await self._client.aclose()

    def _client_or_temp(self) -> httpx.AsyncClient:
        return self._client or httpx.AsyncClient(timeout=300)

    async def send_and_wait(self, message: str, settle_seconds: float = 0.5) -> str | None:
        """
        Manda `message` a `/simulate`, guarda `sim_id`/`run_id` del turno,
        trae y acumula los steps de ese turno (para los accesores de
        validación: `step`, `ran_node`, `state_field`, `branch_taken`), y
        espera `settle_seconds` antes de devolver el reply.
        """
        body = {"message": message, "contact_name": "Simulación E2E"}
        if self.sim_id:
            body["sim_id"] = self.sim_id

        url = f"{self.base_url}/api/flows/bots/{self.bot_id}/simulate"
        if self._client is not None:
            resp = await self._client.post(url, json=body)
        else:
            async with httpx.AsyncClient(timeout=300) as client:
                resp = await client.post(url, json=body)
        resp.raise_for_status()
        data = resp.json()

        self.sim_id = data.get("sim_id") or self.sim_id
        self.last_run_id = data.get("run_id") or self.last_run_id
        if self.last_run_id:
            await self.last_run_steps()

        if settle_seconds:
            await asyncio.sleep(settle_seconds)

        return data.get("reply")

    async def last_run_steps(self) -> list[dict]:
        """
        Steps (`flow_run_steps`) del ÚLTIMO run_id visto (GET /runs/{run_id}).
        Cada turno de `/simulate` genera un run_id nuevo por el hand-off de
        `wait_user` — usa siempre `self.last_run_id`, no el primero visto.
        Cachea el resultado en `self._last_steps` (para `reached_end_conversation()`)
        y lo suma a `self.all_steps` (para validar across-turnos). Ya se llama
        sola desde `send_and_wait` — solo hace falta invocarla a mano si se
        necesita refrescar sin mandar un mensaje nuevo.
        """
        if not self.last_run_id:
            self._last_steps = []
            return self._last_steps
        url = f"{self.base_url}/api/runs/{self.last_run_id}"
        if self._client is not None:
            resp = await self._client.get(url)
        else:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(url)
        resp.raise_for_status()
        self._last_steps = resp.json().get("steps", [])
        self.all_steps.extend(self._last_steps)
        return self._last_steps

    def reached_end_conversation(self) -> bool:
        """True si el ÚLTIMO turno terminó en un nodo end_conversation (cierre real)."""
        return any(s.get("node_type") == "end_conversation" for s in self._last_steps)

    def step(self, node_id: str, occurrence: int = -1) -> dict | None:
        """
        Step de `node_id` en la posición `occurrence` entre TODAS sus
        ejecuciones a lo largo de la conversación (todos los turnos
        acumulados) — None si ese nodo nunca corrió o el índice no existe.

        Un nodo como "Condición" corre UNA VEZ POR TURNO — si se quiere
        validar qué pasó en el primer turno específicamente (ej. "pidió
        aclaración"), hay que pedir `occurrence=0` explícito, no el default
        `-1` (que da la ejecución MÁS RECIENTE, de un turno posterior, y da
        un falso negativo si esa rama cambió más adelante en la conversación).

        Es la base de `ran_node`/`state_field`/`branch_taken`: validar por el
        log real de ejecución (flow_run_steps), no por texto suelto en el reply.
        """
        matches = [s for s in self.all_steps if s.get("node_id") == node_id]
        if not matches:
            return None
        try:
            return matches[occurrence]
        except IndexError:
            return None

    def ran_node(self, node_id: str, status: str = "ok", occurrence: int = -1) -> bool:
        """True si `node_id` corrió (con `status` dado, default 'ok') en la ejecución pedida."""
        s = self.step(node_id, occurrence)
        return bool(s) and s.get("status") == status

    def state_field(self, node_id: str, key: str, occurrence: int = -1):
        """Valor de `state.data[key]` justo después de la ejecución `occurrence` de `node_id`."""
        s = self.step(node_id, occurrence)
        if not s:
            return None
        return (s.get("output_state") or {}).get(key)

    def branch_taken(self, node_id: str, occurrence: int = -1) -> str | None:
        """`branch_taken` logueado en la ejecución `occurrence` de `node_id`."""
        s = self.step(node_id, occurrence)
        return s.get("branch_taken") if s else None

    def has_unresolved_templates(self, *texts: str | None) -> bool:
        """Instancia de la función standalone `has_unresolved_templates` del módulo."""
        return has_unresolved_templates(*texts)

    def state_unresolved_templates(self) -> list[tuple[str, str, str]]:
        """
        Escanea el `output_state` de TODOS los steps de TODOS los turnos
        acumulados (no solo el `reply` final visible al usuario, no solo el
        último turno) buscando placeholders `{{...}}` sin resolver en
        cualquier valor de `state.data`.

        Necesario porque un campo roto (ej. `state.data["direccion"] =
        "{{message}}"`) puede viajar por varios nodos sin aparecer literal en
        el reply final — el LLM a veces reformula en vez de citar el dato tal
        cual, así que chequear solo el texto visible no lo detecta (bug real
        encontrado 2026-07-10: `set_direccion` guardaba `{{message}}` — un
        placeholder que `interpolate()` nunca resuelve, `message` no es un
        campo válido, la convención correcta es `{{conversation.last}}`).

        Devuelve una lista de (node_id, campo, valor) por cada placeholder
        sin resolver encontrado — vacía si no hay ninguno.
        """
        found: list[tuple[str, str, str]] = []
        for step in self.all_steps:
            output = step.get("output_state") or {}
            for key, value in output.items():
                if key == "conversation":
                    continue  # ya cubierto por has_unresolved_templates() sobre replies
                if isinstance(value, str) and _UNRESOLVED_TEMPLATE_RE.search(value):
                    found.append((step.get("node_id", ""), key, value))
        return found
