# Plan: Producción sostenida (Etapa 4)

## Objetivo

Mover el sistema de "corre en la Mac de José" a una infraestructura real, estable y escalable.

## Qué cambia

### Base de datos — SQLite → PostgreSQL
- SQLite es suficiente para la escala actual pero no para multi-empresa con tráfico real
- La migración es transparente para el código: SQLAlchemy ya abstrae el motor
- Momento: cuando haya más de 2-3 empresas activas o tráfico sostenido

### Deploy separado por componente
- Backend Python en servidor Linux (VPS, Railway, Fly.io, etc.)
- Frontend servido desde CDN o el mismo servidor
- DB en servicio gestionado (Supabase, Railway PostgreSQL, etc.)
- Cada componente con su propio proceso y restart automático

### Sesiones WA en servidor
- Las sesiones de Chrome (Playwright) corren en el servidor, no en Mac local
- El perfil de Chrome se persiste en el servidor — misma lógica, distinto disco
- Evaluar si vale la pena Xvfb (pantalla virtual) o browser headless es suficiente

### WhatsApp Business API (futuro)
- Hoy usamos WA Web vía Playwright — funciona pero es frágil (puede romperse si WA cambia el DOM)
- La API oficial de Meta es estable, pero tiene costo y aprobación de cuenta
- Migrar cuando el costo del mantenimiento de WA Web supere el costo de la API oficial
- No es urgente: WA Web funciona bien y la API oficial requiere número dedicado

## Checklist de producción

- [ ] PostgreSQL configurado y migración de esquema
- [ ] Variables de entorno externalizadas (sin `phones.json` hardcodeado)
- [ ] Servidor Linux con Python 3.12 + Playwright instalado
- [ ] Proceso de restart automático (systemd, supervisor, o similar)
- [ ] Backup automático de la DB
- [ ] Monitoreo externo (uptime check)
- [ ] HTTPS para el frontend y el backend

## Estado

No iniciado. Priorizar cuando haya más de 1 empresa de pago activa.
