const TelegramBot = require('node-telegram-bot-api');
const { logMessage, markAnswered } = require('./db');

/**
 * Crea y gestiona un bot de Telegram.
 */
async function createTelegramClient({ botId, token, sessionId, clients, liveConfig }) {
  const tokenId = token.split(':')[0];
  const label = `[${botId}/tg-${tokenId}]`;

  // Detener instancia previa si existe
  const prev = clients[sessionId];
  if (prev?.client) { try { prev.client.stopPolling(); } catch {} }

  clients[sessionId] = {
    status: 'connecting',
    botId,
    number: tokenId,
    client: null,
    isTelegram: true,
    readyTime: null,
  };

  let bot;
  try {
    bot = new TelegramBot(token, { polling: true });
  } catch (err) {
    console.error(`${label} Error al crear bot:`, err.message);
    clients[sessionId].status = 'failed';
    return;
  }

  clients[sessionId].client = bot;

  bot.on('polling_error', (err) => {
    const msg = err.message || err.code || String(err);
    const isNetworkError = ['ETIMEDOUT', 'ECONNRESET', 'ENOTFOUND', 'EFATAL'].some(c => msg.includes(c));
    if (isNetworkError) {
      console.warn(`${label} Polling error (red): ${msg}. Reintentando en 15s...`);
      // No cambiar status — el bot sigue activo, solo hay problema de red temporal
      return;
    }
    console.error(`${label} Polling error fatal:`, msg);
    clients[sessionId].status = 'failed';
    try { bot.stopPolling(); } catch {}
  });

  // Verificar que el token es válido
  try {
    await bot.getMe();
    clients[sessionId].status = 'ready';
    clients[sessionId].readyTime = Date.now();
    const cfg = liveConfig[sessionId] || {};
    const contactsInfo = cfg.allowedContacts?.length > 0 ? cfg.allowedContacts.join(', ') : '(ninguno configurado)';
    console.log(`${label} Bot de Telegram listo. Contactos: ${contactsInfo}`);
  } catch (err) {
    console.error(`${label} Token inválido o error de conexión:`, err.message);
    clients[sessionId].status = 'failed';
    try { bot.stopPolling(); } catch {}
    return;
  }

  bot.on('message', async (msg) => {
    const { readyTime } = clients[sessionId] || {};
    if (readyTime && msg.date * 1000 < readyTime) return;

    const { allowedContacts, replyMessage } = liveConfig[sessionId] || {};
    if (!allowedContacts || allowedContacts.length === 0) return;

    const senderUsername = (msg.from.username || '').toLowerCase();
    const senderId = String(msg.from.id);
    const senderName = msg.from.username || msg.from.first_name || senderId;

    // Match por username (case-insensitive) o user ID numérico string
    const allowed = allowedContacts.some(c => {
      const cLower = String(c).toLowerCase();
      return cLower === senderUsername || cLower === senderId;
    });

    if (!allowed) return;

    const text = msg.text || '';
    // Evitar loop si el mensaje es nuestra propia respuesta automática
    if (text === replyMessage) return;

    const msgId = logMessage(botId, tokenId, senderId, senderName, text);
    console.log(`${label} Mensaje de ${senderName}: "${text}"`);

    try {
      await bot.sendMessage(msg.chat.id, replyMessage);
      markAnswered(msgId);
      console.log(`${label}   → Respuesta enviada (id: ${msgId})`);
    } catch (err) {
      console.error(`${label}   → Error al responder:`, err.message);
    }
  });
}

/**
 * Inicializa todos los bots de Telegram definidos en la config.
 */
async function initTelegramBots(config, clients, liveConfig, createTelegramClientFn) {
  for (const bot of config.bots) {
    for (const tg of (bot.telegram || [])) {
      const tokenId = tg.token.split(':')[0];
      const sessionId = `${bot.id}-tg-${tokenId}`;
      await createTelegramClientFn({ botId: bot.id, token: tg.token, sessionId, clients, liveConfig });
    }
  }
}

module.exports = { createTelegramClient, initTelegramBots };
