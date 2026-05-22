"""
browser_queue — cola observable de operaciones sobre el browser WA por sesión.

Reemplaza _SESSION_BROWSER_LOCKS con un sistema que:
- Serializa acceso al browser (un job a la vez por sesión)
- Expone estado visible al frontend via /api/whatsapp/wa-queue
- Permite cancelar jobs pendientes antes de que empiecen
- Limpia jobs terminados a los 30 segundos
- Aplica timeout de 12 min por job
"""
import asyncio
import dataclasses
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class BrowserJob:
    id: str
    type: str        # "delta_sync" | "full_resync" | "import_wa" | "startup_sync"
    label: str       # nombre del contacto o descripción corta
    session_id: str
    status: str      # "pending" | "running" | "done" | "error" | "cancelled"
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None


class BrowserQueue:
    TIMEOUT_SECONDS = 720  # 12 minutos

    def __init__(self, session_id: str):
        self.session_id = session_id
        self._lock = asyncio.Lock()
        self._jobs: list[BrowserJob] = []

    def enqueue(self, type: str, label: str) -> BrowserJob:
        """Crea y registra un nuevo job en estado pending."""
        job = BrowserJob(
            id=str(uuid.uuid4()),
            type=type,
            label=label,
            session_id=self.session_id,
            status="pending",
            created_at=datetime.now(),
        )
        self._jobs.append(job)
        return job

    async def run(self, job: BrowserJob, coro) -> None:
        """
        Espera el lock, ejecuta coro, marca el job como done/error.
        Si el job fue cancelado antes de adquirir el lock, sale sin ejecutar.
        """
        if job not in self._jobs:
            self._jobs.append(job)
        try:
            async with asyncio.timeout(self.TIMEOUT_SECONDS):
                async with self._lock:
                    if job.status == "cancelled":
                        return
                    job.status = "running"
                    job.started_at = datetime.now()
                    try:
                        await coro
                        job.status = "done"
                    except Exception as exc:
                        job.status = "error"
                        job.error = str(exc)[:200]
                        raise
        except TimeoutError:
            job.status = "error"
            job.error = "timeout (12 min)"
        finally:
            job.finished_at = datetime.now()
            self._trim()

    def cancel(self, job_id: str) -> bool:
        for j in self._jobs:
            if j.id == job_id and j.status == "pending":
                j.status = "cancelled"
                j.finished_at = datetime.now()
                self._trim()
                return True
        return False

    def get_jobs(self) -> list[BrowserJob]:
        self._trim()
        return list(self._jobs)

    def _trim(self) -> None:
        cutoff = datetime.now() - timedelta(seconds=30)
        self._jobs = [
            j for j in self._jobs
            if j.status in ("pending", "running")
            or (j.finished_at is not None and j.finished_at > cutoff)
        ]


# ── Registro global (una queue por session_id) ──────────────────────────────
_QUEUES: dict[str, BrowserQueue] = {}


def get_queue(session_id: str) -> BrowserQueue:
    if session_id not in _QUEUES:
        _QUEUES[session_id] = BrowserQueue(session_id)
    return _QUEUES[session_id]


def all_jobs() -> dict[str, list[dict]]:
    """Devuelve todos los jobs de todas las colas, serializados."""
    result: dict[str, list[dict]] = {}
    for sid, q in _QUEUES.items():
        jobs = q.get_jobs()
        if jobs:
            result[sid] = [dataclasses.asdict(j) for j in jobs]
    return result
