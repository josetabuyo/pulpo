# Roadmap: Contactos y Conversaciones

## Feature: Lista de contactos por empresa

### Concepto
Cada empresa tiene su propia lista de contactos (independiente de los `allowedContacts` de cada bot).
Un contacto es una persona con nombre + uno o más puntos de entrada (número WA, username TG, email en el futuro).

### UI de alta de contactos
- Pantalla/sección de contactos de la empresa
- Formulario de alta: nombre, número WA, username TG (opcional)
- Lista de contactos cargados, con opción de eliminar
- **Contactos propuestos**: al recibir mensajes de números no registrados, aparecen como sugerencia para agregar

### Selección con doble clic
- Al abrir "Contactos permitidos" de un bot, se muestra la lista de contactos de la empresa
- Doble clic en un contacto → se agrega al bot
- Se puede quitar desde la misma lista

### Conversaciones unificadas por empresa
- Una conversación = empresa + contacto (no importa desde qué bot llegó el mensaje)
- Si el mismo contacto escribe por WA y por Telegram, se ve como una sola conversación
- Vista de conversaciones: lista de chats activos por empresa, con todos los mensajes de ese contacto sin importar el canal

### Puntos de entrada de un contacto
- Ahora: número WA, username/ID de Telegram
- Futuro: email

### Modelo de datos sugerido
```
Contacto
  ├── id
  ├── empresa_id
  ├── nombre
  └── channels[]
        ├── type: "whatsapp" | "telegram" | "email"
        └── value: número / username / email

Conversación
  ├── id
  ├── empresa_id
  ├── contacto_id
  └── messages[]
        ├── channel
        ├── direction: "in" | "out"
        ├── body
        └── timestamp
```

## Notas
- El `allowedContacts` actual en cada bot/teléfono debería nutrirse de la lista de contactos de la empresa
- Las conversaciones reemplazarían la tabla `messages` actual (o la extienden)
- Email como canal futuro, no ahora
