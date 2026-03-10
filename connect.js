require('dotenv').config();
const { Client, LocalAuth } = require('whatsapp-web.js');
const { execSync } = require('child_process');
const qrcode = require('qrcode-terminal');
const fs = require('fs');
const path = require('path');

// La limpieza de Chrome se hace por sesión específica antes de conectar cada teléfono

const CONFIG_PATH = path.join(__dirname, 'phones.json');

if (!fs.existsSync(CONFIG_PATH)) {
  console.error('ERROR: No existe phones.json.');
  process.exit(1);
}

const config = JSON.parse(fs.readFileSync(CONFIG_PATH, 'utf8'));
const targetNumber = process.argv[2]; // opcional: conectar solo este número

function hasValidSession(sessionId) {
  const ldbPath = path.join(__dirname, '.wwebjs_auth', `session-${sessionId}`, 'Default', 'Local Storage', 'leveldb');
  if (!fs.existsSync(ldbPath)) return false;
  return fs.readdirSync(ldbPath).some(f => f.endsWith('.ldb'));
}

const phonesToConnect = [];

for (const bot of config.bots) {
  for (const phoneConfig of bot.phones) {
    const { number } = phoneConfig;

    if (targetNumber && number !== targetNumber) continue;

    const sessionId = `${bot.id}-${number}`;

    if (hasValidSession(sessionId)) {
      console.log(`[${bot.id}/${number}] Ya tiene sesión guardada, saltando.`);
      continue;
    }

    // Limpiar solo el Chrome de esta sesión si quedó colgado
    try { execSync(`pkill -f "session-${sessionId}"`, { stdio: 'ignore' }); } catch {}

    phonesToConnect.push({ botId: bot.id, number, sessionId });
  }
}

if (phonesToConnect.length === 0) {
  console.log('Todos los teléfonos ya están conectados. Levantá el server con: npm start');
  process.exit(0);
}

console.log(`Conectando ${phonesToConnect.length} teléfono(s)...`);

let pendingCount = phonesToConnect.length;
const activeClients = [];

for (const { botId, number, sessionId } of phonesToConnect) {
  const label = `[${botId}/${number}]`;

  const client = new Client({
    authStrategy: new LocalAuth({ clientId: sessionId }),
    puppeteer: {
      headless: true,
      executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
      args: ['--no-sandbox', '--disable-setuid-sandbox'],
    },
  });

  activeClients.push(client);

  client.on('qr', (qr) => {
    console.log(`\n${label} Escanea el QR (WhatsApp → Dispositivos vinculados → Vincular dispositivo):\n`);
    qrcode.generate(qr, { small: true });
  });

  client.on('authenticated', async () => {
    console.log(`${label} Autenticado. Sesión guardada.`);
    await new Promise(r => setTimeout(r, 2000));
    try { await client.destroy(); } catch {}
    pendingCount--;
    if (pendingCount === 0) {
      console.log('\nListo. Levantá el server con: npm start');
      process.exit(0);
    }
  });

  client.on('auth_failure', (msg) => {
    console.error(`${label} Error de autenticación:`, msg);
  });

  client.initialize().catch(err => {
    console.error(`${label} Error al inicializar:`, err.message);
  });
}

// Ctrl+C: cerrar Chrome limpiamente antes de salir
process.on('SIGINT', async () => {
  console.log('\nCerrando conexiones...');
  await Promise.allSettled(activeClients.map(c => c.destroy()));
  process.exit(0);
});
