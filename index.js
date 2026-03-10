require('dotenv').config();
const { Client, LocalAuth } = require('whatsapp-web.js');
const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

// Limpiar procesos Chrome colgados de corridas anteriores
try {
  execSync('pkill -f wwebjs_auth', { stdio: 'ignore' });
  execSync('sleep 1');
} catch {}

const { logMessage, markAnswered } = require('./db');

// --- Carga y validación de phones.json ---
const CONFIG_PATH = path.join(__dirname, 'phones.json');

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

// --- Verifica si una sesión está realmente autenticada (tiene datos .ldb de WhatsApp) ---
function hasValidSession(sessionId) {
  const ldbPath = path.join(__dirname, '.wwebjs_auth', `session-${sessionId}`, 'Default', 'Local Storage', 'leveldb');
  if (!fs.existsSync(ldbPath)) return false;
  return fs.readdirSync(ldbPath).some(f => f.endsWith('.ldb'));
}

// --- Config en vivo: sessionId -> { allowedContacts, replyMessage } ---
const liveConfig = {};

function reloadLiveConfig(cfg) {
  for (const bot of cfg.bots) {
    for (const phoneConfig of bot.phones) {
      const sessionId = `${bot.id}-${phoneConfig.number}`;
      liveConfig[sessionId] = {
        allowedContacts: phoneConfig.allowedContacts || [],
        replyMessage: phoneConfig.autoReplyMessage || bot.autoReplyMessage,
      };
    }
  }
}

reloadLiveConfig(config);

// Recarga automática al guardar phones.json (sin reiniciar Chrome)
fs.watch(CONFIG_PATH, (eventType) => {
  if (eventType !== 'change') return;
  try {
    const newConfig = JSON.parse(fs.readFileSync(CONFIG_PATH, 'utf8'));
    reloadLiveConfig(newConfig);
    console.log('[config] phones.json recargado. Cambios aplicados al instante.');
  } catch (err) {
    console.error('[config] Error al recargar phones.json:', err.message);
  }
});

// --- Construye la lista de clientes a inicializar ---
const clientsToInit = [];

for (const bot of config.bots) {
  if (!bot.id || !bot.autoReplyMessage || !Array.isArray(bot.phones)) {
    console.error(`ERROR: Bot mal configurado:`, JSON.stringify(bot));
    process.exit(1);
  }

  for (const phoneConfig of bot.phones) {
    const { number } = phoneConfig;

    if (!number) {
      console.error(`ERROR: Un teléfono en el bot "${bot.id}" no tiene "number".`);
      process.exit(1);
    }

    const sessionId = `${bot.id}-${number}`;
    if (!hasValidSession(sessionId)) {
      console.log(`[${bot.id}/${number}] Sin sesión. Usá 'npm run connect ${number}' para vincular.`);
      continue;
    }

    clientsToInit.push({ botId: bot.id, number, sessionId });
  }
}

// Inicializa los clientes de forma secuencial para evitar que Chrome colisione al arrancar
(async () => {
  for (let i = 0; i < clientsToInit.length; i++) {
    createPhoneClient(clientsToInit[i]);
    if (i < clientsToInit.length - 1) {
      await new Promise(resolve => setTimeout(resolve, 8000));
    }
  }
})();

function createPhoneClient({ botId, number, sessionId }) {
  let botReadyTime = null;
  const label = `[${botId}/${number}]`;

  const client = new Client({
    authStrategy: new LocalAuth({ clientId: sessionId }),
    puppeteer: {
      headless: true,
      executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
      args: ['--no-sandbox', '--disable-setuid-sandbox'],
    },
  });

  client.on('ready', () => {
    botReadyTime = Date.now();
    const { allowedContacts } = liveConfig[sessionId] || {};
    const contactsInfo = allowedContacts && allowedContacts.length > 0
      ? allowedContacts.join(', ')
      : '(ninguno configurado)';
    console.log(`${label} Bot listo. Contactos permitidos: ${contactsInfo}`);
  });

  client.on('auth_failure', (msg) => {
    console.error(`${label} Error de autenticación: ${msg}. Sesión inválida, eliminando...`);
    const sessionPath = path.join(__dirname, '.wwebjs_auth', `session-${sessionId}`);
    try { fs.rmSync(sessionPath, { recursive: true }); } catch {}
    console.error(`${label} Usá 'npm run connect ${number}' para reconectar.`);
  });

  client.on('disconnected', (reason) => {
    console.warn(`${label} Cliente desconectado: ${reason}`);
    if (['LOGOUT', 'UNPAIRED', 'UNPAIRED_IDLE'].includes(reason)) {
      const sessionPath = path.join(__dirname, '.wwebjs_auth', `session-${sessionId}`);
      try {
        fs.rmSync(sessionPath, { recursive: true });
        console.log(`${label} Sesión eliminada. Usá 'npm run connect ${number}' para reconectar.`);
      } catch {}
    }
  });

  client.on('message', async (msg) => {
    // DEBUG: log de todos los mensajes entrantes
    console.log(`${label} [DEBUG] mensaje recibido — from: ${msg.from}, fromMe: ${msg.fromMe}, timestamp: ${msg.timestamp}, body: "${msg.body}"`);

    // Ignorar mensajes propios y de grupos
    if (msg.fromMe || msg.from.endsWith('@g.us')) return;

    // Ignorar mensajes anteriores al inicio del bot
    if (botReadyTime && msg.timestamp * 1000 < botReadyTime) return;

    let senderPhone = msg.from.replace('@c.us', '').replace('@lid', '');
    let name = null;

    try {
      const contact = await msg.getContact();
      name = contact.pushname || contact.name || null;
      if (contact.number) senderPhone = contact.number;
    } catch {}

    const { allowedContacts, replyMessage } = liveConfig[sessionId] || {};

    console.log(`${label} [DEBUG] contacto resuelto — phone: ${senderPhone}, name: "${name}", allowedContacts: ${JSON.stringify(allowedContacts)}`);

    // Si no hay contactos configurados, no responder a nadie
    if (!allowedContacts || allowedContacts.length === 0) return;

    // Solo responder a contactos permitidos (por nombre o por número)
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
    try {
      await client.initialize();
    } catch (err) {
      try { await client.destroy(); } catch {}
      if (attempt <= 3) {
        console.warn(`${label} Error al inicializar (intento ${attempt}/3): ${err.message}. Reintentando en 4s...`);
        await new Promise(r => setTimeout(r, 4000));
        initWithRetry(attempt + 1);
      } else {
        const sessionPath = path.join(__dirname, '.wwebjs_auth', `session-${sessionId}`);
        try { fs.rmSync(sessionPath, { recursive: true }); } catch {}
        console.error(`${label} No se pudo inicializar después de 3 intentos. Sesión eliminada. Usá 'npm run connect ${number}' para reconectar.`);
      }
    }
  };

  initWithRetry();
}
