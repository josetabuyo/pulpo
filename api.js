const express = require('express');
const fs = require('fs');
const path = require('path');
const QRCode = require('qrcode');

module.exports = function createApi({ clients, liveConfig, reloadLiveConfig, createPhoneClient, createTelegramClient, CONFIG_PATH }) {
  const router = express.Router();
  const _connectLock = new Set(); // previene múltiples instancias por número

  const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || 'admin';
  const CLIENT_PASSWORD = process.env.CLIENT_PASSWORD || 'conectar';

  // --- Auth helpers ---
  function isAdmin(req) { return req.headers['x-password'] === ADMIN_PASSWORD; }
  function isClient(req) { return req.headers['x-password'] === CLIENT_PASSWORD || isAdmin(req); }

  function requireAdmin(req, res, next) {
    if (isAdmin(req)) return next();
    res.status(401).json({ error: 'No autorizado' });
  }

  function requireClient(req, res, next) {
    if (isClient(req)) return next();
    res.status(401).json({ error: 'No autorizado' });
  }

  // --- POST /api/auth ---
  router.post('/auth', (req, res) => {
    const { password } = req.body;
    if (password === ADMIN_PASSWORD) return res.json({ ok: true, role: 'admin' });
    if (password === CLIENT_PASSWORD) return res.json({ ok: true, role: 'client' });
    res.status(401).json({ ok: false, error: 'Contraseña incorrecta' });
  });

  // --- Config helpers ---
  function readConfig() {
    return JSON.parse(fs.readFileSync(CONFIG_PATH, 'utf8'));
  }

  function saveConfig(config) {
    fs.writeFileSync(CONFIG_PATH, JSON.stringify(config, null, 2));
    reloadLiveConfig(config);
  }

  // --- GET /api/bots --- (admin) — bots con sus teléfonos y telegram agrupados
  router.get('/bots', requireAdmin, (req, res) => {
    const config = readConfig();
    const result = config.bots.map(bot => ({
      id: bot.id,
      name: bot.name,
      autoReplyMessage: bot.autoReplyMessage,
      phones: bot.phones.map(phone => {
        const sessionId = phone.number;
        return {
          number: phone.number,
          allowedContacts: phone.allowedContacts || [],
          autoReplyMessage: phone.autoReplyMessage || null,
          sessionId,
          status: clients[sessionId]?.status || 'stopped',
        };
      }),
      telegram: (bot.telegram || []).map(tg => {
        const tokenId = tg.token.split(':')[0];
        const sessionId = `${bot.id}-tg-${tokenId}`;
        return {
          tokenId,
          allowedContacts: tg.allowedContacts || [],
          autoReplyMessage: tg.autoReplyMessage || null,
          sessionId,
          status: clients[sessionId]?.status || 'stopped',
        };
      }),
    }));
    res.json(result);
  });

  // --- PUT /api/bots/:botId --- (admin)
  router.put('/bots/:botId', requireAdmin, (req, res) => {
    const { botId } = req.params;
    const { name, autoReplyMessage } = req.body;
    const config = readConfig();
    const bot = config.bots.find(b => b.id === botId);
    if (!bot) return res.status(404).json({ error: 'Bot no encontrado' });
    if (name) bot.name = name;
    if (autoReplyMessage) bot.autoReplyMessage = autoReplyMessage;
    saveConfig(config);
    res.json({ ok: true });
  });

  // --- DELETE /api/bots/:botId --- (admin)
  router.delete('/bots/:botId', requireAdmin, (req, res) => {
    const { botId } = req.params;
    const config = readConfig();
    const bot = config.bots.find(b => b.id === botId);
    if (!bot) return res.status(404).json({ error: 'Bot no encontrado' });
    for (const phone of bot.phones) {
      const sessionId = phone.number;
      if (clients[sessionId]) {
        try { clients[sessionId].client.destroy(); } catch {}
        delete clients[sessionId];
      }
    }
    for (const tg of (bot.telegram || [])) {
      const tokenId = tg.token.split(':')[0];
      const sessionId = `${botId}-tg-${tokenId}`;
      if (clients[sessionId]) {
        try { clients[sessionId].client.stopPolling(); } catch {}
        delete clients[sessionId];
      }
    }
    config.bots = config.bots.filter(b => b.id !== botId);
    saveConfig(config);
    res.json({ ok: true });
  });

  // --- GET /api/phones --- (admin)
  router.get('/phones', requireAdmin, (req, res) => {
    const config = readConfig();
    const result = [];
    for (const bot of config.bots) {
      for (const phone of bot.phones) {
        const sessionId = phone.number;
        result.push({
          botId: bot.id,
          botName: bot.name,
          number: phone.number,
          allowedContacts: phone.allowedContacts || [],
          autoReplyMessage: phone.autoReplyMessage || bot.autoReplyMessage,
          sessionId,
          status: clients[sessionId]?.status || 'stopped',
        });
      }
    }
    res.json(result);
  });

  // --- POST /api/phones --- (admin)
  router.post('/phones', requireAdmin, (req, res) => {
    const { botId, botName, number, allowedContacts, autoReplyMessage } = req.body;
    if (!botId || !number) return res.status(400).json({ error: 'botId y number son requeridos' });

    const config = readConfig();
    let bot = config.bots.find(b => b.id === botId);

    if (!bot) {
      if (!botName || !autoReplyMessage) {
        return res.status(400).json({ error: 'Bot nuevo requiere botName y autoReplyMessage' });
      }
      bot = { id: botId, name: botName, autoReplyMessage, phones: [] };
      config.bots.push(bot);
    }

    // Validar que el número no exista en NINGUNA empresa
    for (const b of config.bots) {
      if (b.phones.find(p => p.number === number)) {
        return res.status(409).json({ error: `El número ya está en la empresa "${b.name}". Movelo desde ahí.` });
      }
    }

    const phoneEntry = { number, allowedContacts: allowedContacts || [] };
    if (autoReplyMessage) phoneEntry.autoReplyMessage = autoReplyMessage;
    bot.phones.push(phoneEntry);

    saveConfig(config);
    res.status(201).json({ ok: true, sessionId: number });
  });

  // --- PUT /api/phones/:number --- (admin)
  router.put('/phones/:number', requireAdmin, (req, res) => {
    const { number } = req.params;
    const { allowedContacts, autoReplyMessage } = req.body;
    const config = readConfig();

    let found = false;
    for (const bot of config.bots) {
      const phone = bot.phones.find(p => p.number === number);
      if (phone) {
        if (allowedContacts !== undefined) phone.allowedContacts = allowedContacts;
        if (autoReplyMessage !== undefined) {
          if (autoReplyMessage) phone.autoReplyMessage = autoReplyMessage;
          else delete phone.autoReplyMessage;
        }
        found = true;
        break;
      }
    }

    if (!found) return res.status(404).json({ error: 'Número no encontrado' });
    saveConfig(config);
    res.json({ ok: true });
  });

  // --- DELETE /api/phones/:number --- (admin)
  router.delete('/phones/:number', requireAdmin, (req, res) => {
    const { number } = req.params;
    const config = readConfig();

    let found = false;
    for (const bot of config.bots) {
      const idx = bot.phones.findIndex(p => p.number === number);
      if (idx !== -1) {
        const sessionId = number;
        if (clients[sessionId]) {
          try { clients[sessionId].client.destroy(); } catch {}
          delete clients[sessionId];
        }
        bot.phones.splice(idx, 1);
        found = true;
        break;
      }
    }

    if (!found) return res.status(404).json({ error: 'Número no encontrado' });
    config.bots = config.bots.filter(b => b.phones.length > 0);
    saveConfig(config);
    res.json({ ok: true });
  });

  // --- POST /api/phones/:number/move --- (admin): mover teléfono a otra empresa
  router.post('/phones/:number/move', requireAdmin, (req, res) => {
    const { number } = req.params;
    const { targetBotId } = req.body;
    if (!targetBotId) return res.status(400).json({ error: 'targetBotId requerido' });

    const config = readConfig();
    const targetBot = config.bots.find(b => b.id === targetBotId);
    if (!targetBot) return res.status(404).json({ error: 'Empresa destino no encontrada' });

    let sourceBot = null;
    let phoneEntry = null;
    for (const b of config.bots) {
      const idx = b.phones.findIndex(p => p.number === number);
      if (idx !== -1) { sourceBot = b; phoneEntry = b.phones.splice(idx, 1)[0]; break; }
    }
    if (!sourceBot) return res.status(404).json({ error: 'Número no encontrado' });
    if (sourceBot.id === targetBotId) return res.status(400).json({ error: 'El teléfono ya está en esa empresa' });

    // La sesión (número) no cambia — solo mueve la config y recarga liveConfig
    targetBot.phones.push(phoneEntry);
    saveConfig(config); // saveConfig llama a reloadLiveConfig internamente

    res.json({ ok: true, from: sourceBot.id, to: targetBotId });
  });

  // --- POST /api/telegram/:tokenId/move --- (admin)
  router.post('/telegram/:tokenId/move', requireAdmin, (req, res) => {
    const { tokenId } = req.params;
    const { targetBotId } = req.body;
    if (!targetBotId) return res.status(400).json({ error: 'targetBotId requerido' });

    const config = readConfig();
    const targetBot = config.bots.find(b => b.id === targetBotId);
    if (!targetBot) return res.status(404).json({ error: 'Empresa destino no encontrada' });

    let sourceBot = null, tgEntry = null;
    for (const b of config.bots) {
      const idx = (b.telegram || []).findIndex(t => t.token.split(':')[0] === tokenId);
      if (idx !== -1) { sourceBot = b; tgEntry = b.telegram.splice(idx, 1)[0]; break; }
    }
    if (!sourceBot) return res.status(404).json({ error: 'Bot de Telegram no encontrado' });
    if (sourceBot.id === targetBotId) return res.status(400).json({ error: 'Ya está en esa empresa' });

    if (!targetBot.telegram) targetBot.telegram = [];
    targetBot.telegram.push(tgEntry);

    // Actualizar sessionId en liveConfig y clients
    const oldSessionId = `${sourceBot.id}-tg-${tokenId}`;
    const newSessionId = `${targetBotId}-tg-${tokenId}`;
    if (liveConfig[oldSessionId]) {
      liveConfig[newSessionId] = liveConfig[oldSessionId];
      delete liveConfig[oldSessionId];
    }
    if (clients[oldSessionId]) {
      clients[newSessionId] = clients[oldSessionId];
      clients[newSessionId].botId = targetBotId;
      delete clients[oldSessionId];
    }

    saveConfig(config);
    res.json({ ok: true, from: sourceBot.id, to: targetBotId });
  });

  // --- POST /api/refresh --- (admin): reconectar clientes caídos post-suspend
  router.post('/refresh', requireAdmin, (req, res) => {
    const config = readConfig();
    let reconnected = 0;
    for (const bot of config.bots) {
      for (const phoneConfig of bot.phones) {
        const sessionId = phoneConfig.number;
        const st = clients[sessionId]?.status;
        if (['disconnected', 'failed', 'stopped'].includes(st) || !st) {
          const hasSession = fs.existsSync(
            path.join(__dirname, '.wwebjs_auth', `session-${sessionId}`, 'Default', 'Local Storage', 'leveldb')
          );
          if (hasSession) {
            if (clients[sessionId]?.client) { try { clients[sessionId].client.destroy(); } catch {} }
            createPhoneClient({ botId: bot.id, number: phoneConfig.number, sessionId, autoStart: true });
            reconnected++;
          }
        }
      }
    }
    res.json({ ok: true, reconnected });
  });

  // --- POST /api/connect/:number --- (client)
  router.post('/connect/:number', requireClient, (req, res) => {
    const { number } = req.params;
    const config = readConfig();

    let found = null;
    for (const bot of config.bots) {
      const phone = bot.phones.find(p => p.number === number);
      if (phone) {
        found = { botId: bot.id, number, sessionId: number };
        break;
      }
    }

    if (!found) return res.status(404).json({ error: 'Número no encontrado. Contactá al administrador.' });

    const { sessionId } = found;
    const existing = clients[sessionId];
    if (_connectLock.has(number) || (existing && ['connecting', 'qr_ready', 'authenticated', 'ready'].includes(existing.status))) {
      return res.json({ ok: true, status: existing?.status || 'connecting', sessionId });
    }

    _connectLock.add(number);
    setTimeout(() => _connectLock.delete(number), 120000); // libera el lock en 2 min máximo

    createPhoneClient(found);
    res.json({ ok: true, status: 'connecting', sessionId });
  });

  // --- GET /api/qr/:sessionId --- (client)
  router.get('/qr/:sessionId', requireClient, async (req, res) => {
    const { sessionId } = req.params;
    const state = clients[sessionId];

    if (!state) return res.status(404).json({ error: 'Sesión no iniciada' });
    if (state.status === 'ready') return res.json({ status: 'ready' });
    if (!state.qr) return res.status(202).json({ status: state.status });

    try {
      const dataUrl = await QRCode.toDataURL(state.qr, { margin: 2 });
      res.json({ qr: dataUrl, status: state.status });
    } catch (err) {
      res.status(500).json({ error: 'Error generando QR' });
    }
  });

  // --- POST /api/telegram --- (admin): agregar bot de Telegram
  router.post('/telegram', requireAdmin, (req, res) => {
    const { botId, token, allowedContacts, autoReplyMessage } = req.body;
    if (!botId || !token) return res.status(400).json({ error: 'botId y token son requeridos' });
    // Validar formato básico del token: número:cadena
    if (!/^\d+:[A-Za-z0-9_-]+$/.test(token)) {
      return res.status(400).json({ error: 'Formato de token inválido (debe ser número:cadena)' });
    }

    const config = readConfig();
    const bot = config.bots.find(b => b.id === botId);
    if (!bot) return res.status(404).json({ error: 'Bot no encontrado' });

    if (!bot.telegram) bot.telegram = [];
    const tokenId = token.split(':')[0];
    if (bot.telegram.find(t => t.token.split(':')[0] === tokenId)) {
      return res.status(409).json({ error: 'Este token ya está registrado' });
    }

    const entry = { token, allowedContacts: allowedContacts || [] };
    if (autoReplyMessage) entry.autoReplyMessage = autoReplyMessage;
    bot.telegram.push(entry);
    saveConfig(config);

    const sessionId = `${botId}-tg-${tokenId}`;
    createTelegramClient({ botId, token, sessionId, clients, liveConfig });

    res.status(201).json({ ok: true, tokenId, sessionId });
  });

  // --- PUT /api/telegram/:tokenId --- (admin): editar allowedContacts y/o autoReplyMessage
  router.put('/telegram/:tokenId', requireAdmin, (req, res) => {
    const { tokenId } = req.params;
    const { allowedContacts, autoReplyMessage } = req.body;
    const config = readConfig();

    let found = false;
    for (const bot of config.bots) {
      const tg = (bot.telegram || []).find(t => t.token.split(':')[0] === tokenId);
      if (tg) {
        if (allowedContacts !== undefined) tg.allowedContacts = allowedContacts;
        if (autoReplyMessage !== undefined) {
          if (autoReplyMessage) tg.autoReplyMessage = autoReplyMessage;
          else delete tg.autoReplyMessage;
        }
        found = true;
        break;
      }
    }

    if (!found) return res.status(404).json({ error: 'Token no encontrado' });
    saveConfig(config);
    res.json({ ok: true });
  });

  // --- DELETE /api/telegram/:tokenId --- (admin): eliminar bot de Telegram
  router.delete('/telegram/:tokenId', requireAdmin, (req, res) => {
    const { tokenId } = req.params;
    const config = readConfig();

    let found = false;
    for (const bot of config.bots) {
      const idx = (bot.telegram || []).findIndex(t => t.token.split(':')[0] === tokenId);
      if (idx !== -1) {
        const sessionId = `${bot.id}-tg-${tokenId}`;
        if (clients[sessionId]) {
          try { clients[sessionId].client.stopPolling(); } catch {}
          delete clients[sessionId];
        }
        bot.telegram.splice(idx, 1);
        found = true;
        break;
      }
    }

    if (!found) return res.status(404).json({ error: 'Token no encontrado' });
    saveConfig(config);
    res.json({ ok: true });
  });

  // --- POST /api/telegram/connect/:tokenId --- (client): iniciar polling si está stopped/failed
  router.post('/telegram/connect/:tokenId', requireClient, (req, res) => {
    const { tokenId } = req.params;
    const config = readConfig();

    let found = null;
    for (const bot of config.bots) {
      const tg = (bot.telegram || []).find(t => t.token.split(':')[0] === tokenId);
      if (tg) {
        found = { botId: bot.id, token: tg.token, sessionId: `${bot.id}-tg-${tokenId}` };
        break;
      }
    }

    if (!found) return res.status(404).json({ error: 'Token no encontrado' });

    const { sessionId } = found;
    const existing = clients[sessionId];
    if (existing && ['connecting', 'ready'].includes(existing.status)) {
      return res.json({ ok: true, status: existing.status, sessionId });
    }

    createTelegramClient({ botId: found.botId, token: found.token, sessionId, clients, liveConfig });
    res.json({ ok: true, status: 'connecting', sessionId });
  });

  // --- GET /api/messages --- (admin)
  router.get('/messages', requireAdmin, (req, res) => {
    const { db } = require('./db');
    const rows = db.prepare('SELECT * FROM messages ORDER BY id DESC LIMIT 100').all();
    res.json(rows);
  });

  return router;
};
