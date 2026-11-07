// WhatsApp para o Alfred.
//   node whatsapp.js                -> MODO=ponte: o Alfred lê conversas e envia (com o seu sim). Não responde sozinho.
//   MODO=atendente node whatsapp.js -> responde clientes sozinho (cérebro gratuito) e registra tudo para o relatório.
// A 1ª vez desenha um QR code aqui no terminal: escaneie em WhatsApp > Aparelhos conectados. A sessão fica salva.
// AVISO: bibliotecas de WhatsApp Web não são oficiais e podem levar ao banimento do número. Use um número dedicado.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { DatabaseSync } = require('node:sqlite');
const qrcode = require('qrcode-terminal');
const { Client, LocalAuth } = require('whatsapp-web.js');
const { criarServidor, idDe } = require('./ponte-http');
const N = require('./atendente-nucleo');

const BASE = path.resolve(__dirname, '..', '..');
const DADOS = path.join(BASE, 'dados');
fs.mkdirSync(DADOS, { recursive: true });
const MODO = process.env.MODO || 'ponte';
const PORTA = +(process.env.PORTA_PONTE || 8787);
const tokenArq = path.join(DADOS, 'ponte.token');
if (!fs.existsSync(tokenArq)) fs.writeFileSync(tokenArq, crypto.randomBytes(24).toString('hex'), { mode: 0o600 });
const TOKEN = fs.readFileSync(tokenArq, 'utf8').trim();

const client = new Client({
  authStrategy: new LocalAuth({ clientId: 'alfred', dataPath: path.join(DADOS, 'whatsapp-sessao') }),
  puppeteer: { args: ['--no-sandbox', '--disable-dev-shm-usage'] },
});
client.on('qr', (qr) => { console.log('\nEscaneie este QR code no WhatsApp (Aparelhos conectados):\n'); qrcode.generate(qr, { small: true }); });
client.on('ready', () => console.log(`WhatsApp conectado (modo ${MODO}).`));
client.on('disconnected', (m) => console.log('WhatsApp desconectado:', m));

if (MODO === 'atendente') {
  const GROQ = process.env.ALFRED_CHAVE_GROQ;
  if (!GROQ) { console.error('Defina ALFRED_CHAVE_GROQ (o launcher lê do cofre). Veja LEIA-ME.md'); process.exit(1); }
  const dir = path.join(BASE, 'atendente');
  const lerArq = (n, alt) => (fs.existsSync(path.join(dir, n)) ? fs.readFileSync(path.join(dir, n), 'utf8') : fs.readFileSync(path.join(BASE, 'presets', 'atendente', alt), 'utf8'));
  const PROMPT = lerArq('prompt.txt', 'prompt.txt');
  const NEGOCIO = lerArq('negocio.md', 'negocio.exemplo.md');
  const db = new DatabaseSync(path.join(DADOS, 'atendimento.db'));
  db.exec(`CREATE TABLE IF NOT EXISTS mensagens (id INTEGER PRIMARY KEY, quando TEXT DEFAULT (datetime('now','localtime')), conversa TEXT NOT NULL,
    quem TEXT CHECK (quem IN ('cliente','atendente','humano')), texto TEXT NOT NULL, modelo TEXT, humano INTEGER DEFAULT 0, ms INTEGER);
    CREATE INDEX IF NOT EXISTS idx_msg_quando ON mensagens(quando); CREATE INDEX IF NOT EXISTS idx_msg_conversa ON mensagens(conversa);`);
  const ins = db.prepare('INSERT INTO mensagens (conversa, quem, texto, modelo, humano, ms) VALUES (?,?,?,?,?,?)');
  const hist = db.prepare('SELECT quem, texto FROM mensagens WHERE conversa=? ORDER BY id DESC LIMIT 12');
  const ult = db.prepare("SELECT texto FROM mensagens WHERE conversa=? AND quem='atendente' ORDER BY id DESC LIMIT 3");
  const pausados = new Map();
  const SIMULACAO = process.env.SIMULACAO === '1';
  const DONO = process.env.NUMERO_DONO; // ex.: 5548999999999@c.us (recebe o aviso de chamado humano)

  client.on('message', async (msg) => {
    if (msg.fromMe || msg.from.endsWith('@g.us') || msg.from === 'status@broadcast') return;
    if ((pausados.get(msg.from) || 0) > Date.now()) return;
    const t0 = Date.now();
    const entrada = msg.body || '[mídia sem texto]';
    ins.run(msg.from, 'cliente', entrada, null, 0, null);
    const historico = hist.all(msg.from).reverse().map((m) => ({ role: m.quem === 'cliente' ? 'user' : 'assistant', content: m.texto }));
    const { texto, modelo } = await N.pensar({ prompt: N.montarPrompt(PROMPT, NEGOCIO), historico, chave: GROQ });
    const humano = N.ehHumano(texto);
    const final = N.semRepeticao(N.limpar(texto), ult.all(msg.from).map((x) => x.texto), 'Vou pedir para a nossa equipe te ajudar com isso, ok?');
    const chat = await msg.getChat();
    for (const parte of N.partes(final)) {
      if (SIMULACAO) { console.log('[simulação]', parte); continue; }
      await chat.sendStateTyping(); await new Promise((r) => setTimeout(r, N.pausaDigitando(parte))); await client.sendMessage(msg.from, parte);
    }
    ins.run(msg.from, 'atendente', final, modelo, humano ? 1 : 0, Date.now() - t0);
    if (humano) {
      pausados.set(msg.from, Date.now() + 6 * 3600 * 1000); // 6 h em silêncio nessa conversa
      if (!SIMULACAO && DONO) await client.sendMessage(DONO, `Cliente ${msg.from} precisa de você:\n"${entrada.slice(0, 200)}"`);
    }
  });
}

const servidor = criarServidor({ client, token: TOKEN });
servidor.listen(PORTA, '127.0.0.1', () => console.log(`Ponte do Alfred em http://127.0.0.1:${PORTA} (token em dados/ponte.token)`));
client.initialize();
