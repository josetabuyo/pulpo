# Visión del Proyecto — Pulpo

## El nombre

**Pulpo** — Una plataforma multi-canal al servicio de empresas y personas.

El pulpo tiene muchos brazos: cada uno es un canal de comunicación. WhatsApp, Telegram, Instagram, email — todos coordinados desde un solo centro. La visión es una plataforma que gestiona múltiples bots, para múltiples empresas, sobre múltiples canales de comunicación.

---

## La misión

> Llevar tecnología de punta a cualquier empresa, sin importar su tamaño ni su presupuesto.

Desde el que no puede pagar WhatsApp Business hasta el que quiere lo mejor y está dispuesto a pagar por ello — la plataforma es la misma. Lo que cambia es qué features tiene habilitadas. El software hoy es casi gratis, y eso permite que lo que antes era solo para grandes empresas esté al alcance de cualquiera con un celular.

---

## Las entidades clave

### Empresa

La unidad central. Todo lo demás le pertenece.

### Clientes

La lista de personas con quienes la empresa se comunica. Un cliente pertenece a la empresa, no a un bot ni a un número. Si la misma persona escribe por WhatsApp o por Telegram, es el mismo cliente.

### Puntos de entrada

Por dónde le llegan mensajes a la empresa. Hoy tenemos dos:

- **WhatsApp Web** — un número de celular, puede ser personal o exclusivo para el bot
- **Telegram** — un bot de Telegram

Mañana habrá más: Instagram DM, email, WhatsApp Business, lo que venga. Cada empresa puede tener varios puntos de entrada. Todos comparten la misma base de clientes.

### Servicios

Lo que la empresa ofrece a sus clientes. Pueden ser generales (aplican a todos los puntos de entrada) o específicos por punto de entrada. Hoy: respuesta automática fuera de horario. Mañana: más features activadas según lo que corresponda.

---

## Cómo se incorporan clientes

Los clientes pertenecen a la empresa, no al bot ni al canal. Hay múltiples formas de incorporarlos:

1. **Desde los contactos del celular** — al configurar un punto de entrada (teléfono), el sistema sugiere los contactos de ese teléfono como clientes potenciales. Es una fuente de datos, no la única.
2. **Manualmente desde la UI** — la empresa agrega clientes con un formulario: nombre + canales de contacto.
3. **Futuro: desde el primer mensaje** — un cliente escribe por primera vez y aparece como sugerencia para agregar.

---

## El modelo de features

Cada empresa no tiene "su propia lógica" — tiene el mismo producto, con features que se activan de a poco.

El modelo es acumulativo: empezás con lo más simple y vas sumando. Ninguna empresa programa nada, ni configura features por su cuenta. El admin de la plataforma habilita cada feature para cada empresa — en el futuro eso puede traducirse en un plan de suscripción, pero hoy todo es gratuito.

### Features, de menor a mayor complejidad

| # | Feature | Descripción |
|---|---------|-------------|
| 1 | **Respuesta automática** | Un mensaje fijo cuando alguien escribe fuera de horario o sin atención |
| 2 | **Gestión de clientes** | Lista de contactos de la empresa, con canales y estado |
| 3 | **Modo de trabajo por chat** | El operador gestiona y responde conversaciones desde el mismo WhatsApp o panel |
| 4 | **Alertas de no atención** | Notificación si un mensaje no fue respondido en X minutos |
| 5 | **Menú de opciones** | El bot presenta opciones al cliente y ramifica según respuesta |
| 6 | **Bot con IA** | Se activa un modelo tipo Claude que responde con contexto, reemplazando o asistiendo al operador |

Cada empresa avanza en este camino a su ritmo. La plataforma es la misma para todos — lo que cambia es qué tienen habilitado.

---

## Modelo de negocio

- **Gratis** para amigos y proyectos propios
- **Pago** para empresas externas que quieran el servicio
- El valor está en la gestión, la confiabilidad y el soporte — no en el código en sí

---

## Lo que ya tenemos

| Cosa | Estado |
|------|--------|
| Bot Telegram (Python) | ✅ funcionando |
| Bot WA multi-teléfono (Node.js adaptador) | ⚠️ pendiente migrar a microservicio |
| DB SQLite con mensajes | ✅ funcionando |
| API REST (FastAPI) | ✅ funcionando |
| Panel admin React | ✅ funcionando — login, dashboard, connect QR |
| Tests de Playwright | ✅ login, proxy, dashboard |
| Watchdog de reconexión WA | ⚠️ en revisión |
| Adaptador WA como microservicio | 🔜 Etapa 2 |
| Clientes por empresa en DB | 🔜 planeado |
| Conversaciones unificadas por cliente | 🔜 planeado |
| Respuesta desde el panel | 🔜 planeado |
| Alertas de no atención | 🔜 planeado |
| Menú de opciones para el cliente | 🔜 futuro |
| Feature: bot con IA (tipo Claude) | 🔜 horizonte lejano |

---

## Clientes actuales (fase gratuita)

- **GH Herrería** — bot de guardia, atiende consultas fuera de horario
- **Segunda empresa** — en configuración

---

## Hoja de ruta macro

### Ahora — Estabilizar la base
- Resolver watchdog (`ESTADO_WATCHDOG.md`)
- Implementar clientes por empresa en DB (`PLAN_CONTACTOS.md`)

### Próximo — Experiencia completa
- Conversaciones unificadas (un hilo por cliente, sin importar el canal)
- Respuesta manual desde el panel admin
- Alertas: si no se respondió en X minutos → notificar

### Después — Producto
- Multi-empresa con login propio
- Planes y billing
- Onboarding de nuevas empresas sin tocar código
- Más puntos de entrada (Instagram DM, email)
- Mensajes con opciones y flujos configurables

### Horizonte
- Feature: bot con IA activable por empresa (tipo Claude)
- El bot no solo responde — guía, califica, resuelve, sin que la empresa toque nada técnico

---

## Qué NO es esto

- No es un CRM completo (aunque puede parecerse en el futuro)
- No es un servicio de spam o marketing masivo
- No reemplaza la atención humana — la organiza y la complementa
- La tecnología detrás no importa al usuario final: solo tiene un celular

---

*Documento vivo. Se actualiza conforme evoluciona la visión.*
