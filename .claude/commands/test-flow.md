# /test-flow — Test e2e de un flow via Teli

Prueba rápida de un flow de Telegram mandando un mensaje real y verificando los logs.

## Uso

```
/test-flow
/test-flow bot=@luganense_bot mensaje="donde hay una ferreteria?"
```

Si no se pasan argumentos, usar los defaults: bot `@luganense_bot`, mensaje `"donde hay una ferreteria?"`.

---

## Paso 1 — Verificar que el backend está up y el bot está conectado

```bash
curl -s http://localhost:8000/health
```

Luego confirmar que el bot tiene status "ready" (no "stopped"):

```bash
curl -s http://localhost:8000/api/bots | python3 -m json.tool | grep -A3 "luganense"
```

Si el bot está "stopped": el lifespan no arrancó los bots. Reiniciar:

```bash
cd /Users/josetabuyo/Development/pulpo/_ && ./restart-backend.sh && sleep 12
```

Verificar en el log que aparezca `[luganense/tg-8502732053] Bot de Telegram listo`:

```bash
grep "Bot de Telegram listo" /Users/josetabuyo/Development/pulpo/_/monitor/backend.log | tail -5
```

---

## Paso 2 — Enviar el mensaje de prueba

```bash
teli user send @luganense_bot "donde hay una ferreteria?"
```

Confirmar que dice `Mensaje enviado a '@luganense_bot'.`

---

## Paso 3 — Esperar y leer los logs

```bash
sleep 20
```

Luego buscar la ejecución del flow:

```bash
grep -E "Mensaje de|RouterNode.*route|FetchNode.*http|LLMNode|reply" /Users/josetabuyo/Development/pulpo/_/monitor/backend.log | tail -15
```

### Qué esperar ver (flow "Orquestador Vendedor" de Luganense)

```
[luganense/tg-8502732053] Mensaje de José: "donde hay una ferreteria?"
[RouterNode] route → 'directorio'
[FetchNode] http https://luganense.vercel.app/api/directorio/buscar?q=... → NNN chars
```

Si aparece `route → 'directorio'` y el FetchNode llamó al endpoint, el flow del directorio funciona.

---

## Paso 4 — Reportar resultado

Mostrar al usuario:
- ¿El mensaje llegó al bot? (log line `Mensaje de ...`)
- ¿Qué ruta tomó el router? (`route → '...'`)
- ¿Qué respondió el endpoint? (chars del FetchNode)
- ¿Hubo errores? (buscar `ERROR` en el tramo del log)

---

## Notas

- `teli user send <destinatario> <mensaje>` — no requiere nombre de conexión (Teli v0.2.0+)
- El bot que recibe es `@luganense_bot` (token_id `8502732053`, connection_id `luganense`)
- El flow "Orquestador Vendedor" tiene branches: `servicio`, `producto`, `directorio`, `noticias`
- URL del directorio: `https://luganense.vercel.app/api/directorio/buscar?q={message}`
- Si el endpoint devuelve 0 resultados, el LLM igual responde (con "no encontré nada")
