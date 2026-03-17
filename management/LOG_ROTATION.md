# Rotación de logs — deuda técnica conocida

## El problema

Los logs del backend se escriben a `monitor/backend.log` sin límite de tamaño.
En producción con tráfico normal (~30-100 líneas/min), el archivo puede llegar
a varios cientos de MB en semanas. Esto tiene dos consecuencias:

- **Disco lleno**: riesgo real en servidores con poco espacio
- **Lecturas lentas**: el endpoint `/api/logs/latest` usa `deque()` que lee el
  archivo completo antes de quedarse con las últimas N líneas

## La solución

Reemplazar el `FileHandler` actual por `RotatingFileHandler` en la configuración
de logging del backend. Esto mantiene el archivo bajo un tamaño fijo y rota
automáticamente a archivos backup.

```python
# backend/main.py — reemplazar el basicConfig actual
import logging
from logging.handlers import RotatingFileHandler

LOG_PATH = os.path.join(PROJECT_DIR, "monitor", "backend.log")
handler = RotatingFileHandler(
    LOG_PATH,
    maxBytes=5 * 1024 * 1024,  # 5 MB por archivo
    backupCount=3,              # mantiene backend.log + .1 + .2 + .3
    encoding="utf-8",
)
handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
logging.basicConfig(handlers=[handler], level=logging.INFO)
```

Esto limita el espacio total a ~20 MB para los logs del backend.

## Estado

Pendiente. El sistema funciona correctamente hoy — solo es un riesgo a mediano
plazo. Priorizar cuando el servidor esté en producción sostenida por más de
2-3 semanas.

## Nota sobre el API

El endpoint `/api/logs/latest` acepta hasta 5000 líneas. Para ventanas de tiempo
largas (3h) con tráfico alto, puede no cubrir toda la ventana. La solución
definitiva sería filtrar por timestamp en el backend en lugar de pedir N líneas.
Eso es una mejora separada.
