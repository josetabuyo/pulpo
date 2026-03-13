require('dotenv').config();
const { Client, LocalAuth } = require('whatsapp-web.js');
const { execSync } = require('child_process');
const express = require('express');
const fs = require('fs');
const path = require('path');

const { logMessage, markAnswered } = require('./db');
const createApi = require('./api');
const { createTelegramClient, initTelegramBots } = require('./telegram');

// Timestamps en todos los logs
const _log = console.log.bind(console);
const _warn = console.warn.bind(console);
const _error = console.error.bind(console);
const ts = () => new Date().toLocaleString('es-AR', { hour12: false, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' });
console.log   = (...a) => _log(`[${ts()}]`, ...a);
console.warn  = (...a) => _warn(`[${ts()}]`, ...a);
console.error = (...a) => _error(`[${ts()}]`, ...a);

// Errores de Puppeteer/WA que no deben tirar el proceso
// Cierre limpio al recibir SIGINT (Ctrl+C) — permite que Chrome escriba la sesión a disco
process.on('SIGINT', () => {
  console.log('\n[shutdown] Cerrando clientes...');

  // Safety net: si en 6s no terminó, matar igual
  const forceExit = setTimeout(() => {
    try { execSync('pkill -f ".wwebjs_auth" 2>/dev/null || true', { stdio: 'ignore' }); } catch {}
    console.log('[shutdown] Timeout — salida forzada.');
    process.exit(0);
  }, 6000);
  forceExit.unref();

  const tasks = Object.values(clients).map(c => {
    if (!c?.client) return Promise.resolve();
    try {
      if (c.isTelegram) return Promise.resolve(c.client.stopPolling()).catch(() => {});
      return c.client.destroy().catch(() => {});
    } catch { return Promise.resolve(); }
  });

  Promise.allSettled(tasks).then(() => {
    try { execSync('pkill -f ".wwebjs_auth" 2>/dev/null || true', { stdio: 'ignore' }); } catch {}
    console.log('[shutdown] Listo. Bye!');
    process.exit(0);
  });
});

const RECOVERABLE_ERRORS = ['ProtocolError', 'Target closed', 'Execution context was destroyed', 'Session closed'];

process.on('uncaughtException', (err) => {
  const isRecoverable = RECOVERABLE_ERRORS.some(msg => err.message?.includes(msg) || err.name?.includes(msg));
  if (isRecoverable) {
    console.warn('[uncaughtException] Error recuperable de Puppeteer ignorado:', err.message);
  } else {
    console.error('[uncaughtException] Error crítico — cerrando proceso:', err);
    process.exit(1);
  }
});

process.on('unhandledRejection', (reason) => {
  const msg = reason?.message || String(reason);
  const isRecoverable = RECOVERABLE_ERRORS.some(r => msg.includes(r));
  if (isRecoverable) {
    console.warn('[unhandledRejection] Promesa rechazada recuperable ignorada:', msg);
  } else {
    console.error('[unhandledRejection] Promesa rechazada crítica:', msg);
  }
});

// Limpiar procesos Chrome colgados de corridas anteriores
try { execSync('pkill -9 -f wwebjs_auth 2>/dev/null; sleep 2', { stdio: 'ignore' }); } catch {}

const CONFIG_PATH = path.join(__dirname, 'phones.json');
const PORT = process.env.PORT || 3000;
const CHROME_PATH = process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';

if (!fs.existsSync(CONFIG_PATH)) {
  console.error('ERROR: No existe phones.json. Copia phones.example.json y complétalo.');
  process.exit(1);
}

let config;
try {
  config = JSON.parse(fs.readFileSync(CONFIG_PATH, 'utf8'));
} catch (err) {
  console.error('ERROR: phones.json tiene formato inválido:', err.message);
  process.exit(1);
}

if (!config.bots || !Array.isArray(config.bots) || config.bots.length === 0) {
  console.error('ERROR: phones.json debe tener al menos un bot en "bots".');
  process.exit(1);
}

// --- Estado compartido de clientes ---
// sessionId -> { client, status, qr, botId, number, readyTime }
// status: 'connecting' | 'qr_ready' | 'authenticated' | 'ready' | 'disconnected' | 'failed'
const clients = {};

// Generación por sessionId — detecta y silencia event handlers de instancias zombie
const _clientGen = {};

// --- Config en vivo ---
const liveConfig = {};

function reloadLiveConfig(cfg) {
  for (const bot of cfg.bots) {
    for (const phoneConfig of bot.phones) {
      const sessionId = phoneConfig.number;
      liveConfig[sessionId] = {
        allowedContacts: phoneConfig.allowedContacts || [],
        replyMessage: phoneConfig.autoReplyMessage || bot.autoReplyMessage,
      };
    }
    for (const tg of (bot.telegram || [])) {
      const tokenId = tg.token.split(':')[0];
      const sessionId = `${bot.id}-tg-${tokenId}`;
      liveConfig[sessionId] = {
        allowedContacts: tg.allowedContacts || [],
        replyMessage: tg.autoReplyMessage || bot.autoReplyMessage,
      };
    }
  }
}

reloadLiveConfig(config);

fs.watch(CONFIG_PATH, (eventType) => {
  if (eventType !== 'change') return;
  try {
    const newConfig = JSON.parse(fs.readFileSync(CONFIG_PATH, 'utf8'));
    reloadLiveConfig(newConfig);
    console.log('[config] phones.json recargado.');
  } catch (err) {
    console.error('[config] Error al recargar phones.json:', err.message);
  }
});

// --- Verifica sesión guardada ---
function hasValidSession(number) {
  const ldbPath = path.join(__dirname, '.wwebjs_auth', `session-${number}`, 'Default', 'Local Storage', 'leveldb');
  if (!fs.existsSync(ldbPath)) return false;
  return fs.readdirSync(ldbPath).some(f => f.endsWith('.ldb') || f.endsWith('.log'));
}

// --- Crea y gestiona un cliente WA ---
// autoStart=true → arrancado al inicio (sesión guardada). Si pide QR, la sesión expiró → destruir silenciosamente.
// autoStart=false → iniciado desde la UI por el usuario → mostrar QR.
async function createPhoneClient({ botId, number, autoStart = false }) {
  const sessionId = number;
  const label = `[${botId}/${number}]`;

  // Incrementar generación — event handlers de instancias anteriores se descartarán
  const gen = (_clientGen[sessionId] = (_clientGen[sessionId] || 0) + 1);
  const isCurrent = () => _clientGen[sessionId] === gen;

  console.log(`${label} Iniciando sesión WhatsApp... (abriendo Chrome, puede tardar 1-2 min)`);

  // Bloquear inmediatamente para evitar race conditions
  const prevClient = clients[sessionId]?.client;
  clients[sessionId] = { status: 'connecting', qr: null, botId, number, client: null, readyTime: null };

  // Destruir instancia previa
  if (prevClient) {
    try { await prevClient.destroy(); } catch {}
  }
  // Matar cualquier Chrome zombie que use este directorio de sesión (más confiable que destroy())
  try { execSync(`pkill -f "session-${number}" 2>/dev/null || true`, { stdio: 'ignore' }); } catch {}
  await new Promise(r => setTimeout(r, 2000));

  const client = new Client({
    authStrategy: new LocalAuth({ clientId: sessionId }),
    puppeteer: {
      headless: true,
      executablePath: CHROME_PATH,
      args: ['--no-sandbox', '--disable-setuid-sandbox'],
    },
  });

  clients[sessionId].client = client;

  // Flags one-shot: whatsapp-web.js puede disparar estos eventos más de una vez
  let authFired = false;
  let readyFired = false;

  client.on('qr', (qr) => {
    if (!isCurrent()) return;
    if (autoStart) {
      // Sesión local expirada en WhatsApp — no mostrar QR, esperar acción del usuario
      console.log(`${label} Sesión expirada. Reconectá desde http://localhost:${PORT}`);
      clients[sessionId].status = 'stopped';
      clients[sessionId].qr = null;
      clients[sessionId]._intentionalStop = true;
      // Destruir Chrome ANTES de borrar los archivos — si no, Chrome los recrea
      client.destroy().catch(() => {}).finally(() => {
        const sessionPath = path.join(__dirname, '.wwebjs_auth', `session-${number}`);
        try { fs.rmSync(sessionPath, { recursive: true }); } catch {}
      });
      return;
    }
    // Conexión iniciada desde la UI → mostrar QR (solo si no autenticó aún)
    if (authFired) return;
    console.log(`${label} QR generado.`);
    clients[sessionId].qr = qr;
    clients[sessionId].status = 'qr_ready';
  });

  client.on('authenticated', () => {
    if (!isCurrent() || authFired) return;
    authFired = true;
    console.log(`${label} Autenticado. Sesión guardada.`);
    clients[sessionId].status = 'authenticated';
    clients[sessionId].qr = null;
  });

  client.on('ready', () => {
    if (!isCurrent() || readyFired) return;
    readyFired = true;
    const readyTime = Date.now();
    clients[sessionId].status = 'ready';
    clients[sessionId].readyTime = readyTime;
    clients[sessionId].qr = null;
    const { allowedContacts } = liveConfig[sessionId] || {};
    const contactsInfo = allowedContacts?.length > 0 ? allowedContacts.join(', ') : '(ninguno configurado)';
    console.log(`${label} Bot listo. Contactos: ${contactsInfo}`);
  });

  client.on('auth_failure', (msg) => {
    if (!isCurrent()) return;
    console.error(`${label} Error de autenticación: ${msg}. Eliminando sesión...`);
    clients[sessionId].status = 'failed';
    clients[sessionId].qr = null;
    const sessionPath = path.join(__dirname, '.wwebjs_auth', `session-${sessionId}`);
    try { fs.rmSync(sessionPath, { recursive: true }); } catch {}
  });

  client.on('disconnected', (reason) => {
    if (!isCurrent()) return;
    console.warn(`${label} Desconectado: ${reason}`);
    clients[sessionId].status = 'disconnected';
    clients[sessionId].qr = null;
    if (['LOGOUT', 'UNPAIRED', 'UNPAIRED_IDLE'].includes(reason)) {
      const sessionPath = path.join(__dirname, '.wwebjs_auth', `session-${sessionId}`);
      try { fs.rmSync(sessionPath, { recursive: true }); } catch {}
      console.log(`${label} Sesión eliminada. Reconectá desde la UI.`);
    } else {
      // Reconectar automáticamente usando la sesión guardada (sin QR)
      console.log(`${label} Desconexión recuperable. Reconectando en 5s...`);
      setTimeout(() => {
        if (!isCurrent()) return;
        createPhoneClient({ botId, number, autoStart: true });
      }, 5000);
    }
  });

  // message_create captura todos los mensajes nuevos (más confiable que 'message')
  client.on('message_create', async (msg) => {
    if (!isCurrent()) return;

    // Ignorar grupos y direcciones LID (dispositivos vinculados, número no confiable)
    if (msg.from.endsWith('@g.us')) return;
    if (msg.from.endsWith('@lid')) return;
    // Ignorar respuestas del bot a otros (evita loop), pero permitir mensajes propios (debugging)
    if (msg.fromMe && msg.to !== msg.from) return;

    const { readyTime } = clients[sessionId] || {};
    if (readyTime && msg.timestamp * 1000 < readyTime) return;

    let senderPhone = msg.from.replace('@c.us', '').replace('@lid', '');
    let name = null;

    try {
      const contact = await msg.getContact();
      name = contact.pushname || contact.name || null;
      if (contact.number) senderPhone = contact.number;
    } catch {}

    const { allowedContacts, replyMessage } = liveConfig[sessionId] || {};

    // Evitar loop: no responder si el mensaje ES nuestra propia respuesta automática
    if (msg.body === replyMessage) return;

    if (!allowedContacts || allowedContacts.length === 0) return;
    if (!allowedContacts.includes(name) && !allowedContacts.includes(senderPhone)) return;

    const msgId = logMessage(botId, number, senderPhone, name, msg.body);
    console.log(`${label} [${new Date().toISOString()}] Mensaje de ${name || senderPhone}: "${msg.body}"`);

    try {
      await msg.reply(replyMessage);
      markAnswered(msgId);
      console.log(`${label}   → Respuesta enviada (id: ${msgId})`);
    } catch (err) {
      console.error(`${label}   → Error al responder:`, err.message);
    }
  });

  const initWithRetry = async (attempt = 1) => {
    if (!isCurrent()) return;
    try {
      await client.initialize();
    } catch (err) {
      if (!isCurrent()) return;
      if (clients[sessionId]?._intentionalStop) return;
      try { await client.destroy(); } catch {}
      if (attempt <= 3) {
        console.warn(`${label} Error al inicializar (intento ${attempt}/3): ${err.message}. Reintentando en 4s...`);
        await new Promise(r => setTimeout(r, 4000));
        initWithRetry(attempt + 1);
      } else {
        clients[sessionId].status = 'failed';
        const sessionPath = path.join(__dirname, '.wwebjs_auth', `session-${sessionId}`);
        try { fs.rmSync(sessionPath, { recursive: true }); } catch {}
        console.error(`${label} Falló después de 3 intentos. Reconectá desde la UI.`);
      }
    }
  };

  initWithRetry();
}

// --- Express ---
const app = express();
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));
app.use('/api', createApi({ clients, liveConfig, reloadLiveConfig, createPhoneClient, createTelegramClient, CONFIG_PATH }));

app.get('/connect', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'connect.html'));
});

app.listen(PORT, () => {
  console.log(`Servidor corriendo en http://localhost:${PORT}`);
  initTelegramBots(config, clients, liveConfig, createTelegramClient);
});

// Watchdog: detecta clientes WA muertos y los reconecta automáticamente
setInterval(async () => {
  const cfg = JSON.parse(fs.readFileSync(CONFIG_PATH, 'utf8'));
  for (const bot of cfg.bots) {
    for (const phoneConfig of bot.phones) {
      const sessionId = phoneConfig.number;
      const session = clients[sessionId];
      if (!session || session.status !== 'ready') continue;
      // Grace period: skip check for 2 min after ready (state can be OPENING or null)
      if (session.readyTime && Date.now() - session.readyTime < 120000) continue;
      try {
        const state = await session.client.getState();
        // null = client still initializing, OPENING = transitioning — skip both
        if (state === null || state === 'OPENING') continue;
        if (state !== 'CONNECTED') throw new Error(state);
      } catch (err) {
        console.warn(`[${bot.id}/${sessionId}] Watchdog: cliente caído (${err.message}). Reconectando...`);
        createPhoneClient({ botId: bot.id, number: phoneConfig.number, autoStart: true });
      }
    }
  }
}, 30000);

// --- Inicializar clientes con sesión válida al arrancar ---
const clientsToInit = [];

for (const bot of config.bots) {
  if (!bot.id || !bot.autoReplyMessage || !Array.isArray(bot.phones)) {
    console.error(`ERROR: Bot mal configurado:`, JSON.stringify(bot));
    process.exit(1);
  }
  for (const phoneConfig of bot.phones) {
    const { number } = phoneConfig;
    if (!number) { console.error(`ERROR: número faltante en bot "${bot.id}".`); process.exit(1); }
    if (!hasValidSession(number)) {
      console.log(`[${bot.id}/${number}] Sin sesión. Vinculá desde http://localhost:${PORT}`);
      continue;
    }
    clientsToInit.push({ botId: bot.id, number, autoStart: true });
  }
}

(async () => {
  for (let i = 0; i < clientsToInit.length; i++) {
    createPhoneClient(clientsToInit[i]);
    if (i < clientsToInit.length - 1) {
      await new Promise(resolve => setTimeout(resolve, 8000));
    }
  }
})();
