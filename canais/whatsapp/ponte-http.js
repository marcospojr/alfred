// Servidor HTTP local (127.0.0.1) que deixa o Alfred ler conversas e enviar mensagens pelo WhatsApp.
// Só aceita requisições com o token de dados/ponte.token e Host local. Enviar = ação vermelha no Alfred (ele pede o seu sim).
const http = require('node:http');

const idDe = (id) => (id && (id._serialized ?? id.$1)) || String(id); // a lib renomeou _serialized em algumas versões

function criarServidor({ client, token, rascunhos = new Map() }) {
  const json = (res, code, obj) => { res.writeHead(code, { 'content-type': 'application/json; charset=utf-8' }); res.end(JSON.stringify(obj)); };
  const corpo = (req) => new Promise((ok, erro) => { let b = ''; req.on('data', (c) => { b += c; if (b.length > 100_000) req.destroy(); }); req.on('end', () => { try { ok(JSON.parse(b || '{}')); } catch (e) { erro(e); } }); });

  return http.createServer(async (req, res) => {
    try {
      const host = (req.headers.host || '').split(':')[0];
      if (host !== '127.0.0.1' && host !== 'localhost') return json(res, 403, { erro: 'host' });
      if (req.headers['x-token'] !== token) return json(res, 401, { erro: 'token' });
      const u = new URL(req.url, 'http://127.0.0.1');
      if (req.method === 'GET' && u.pathname === '/conversas') {
        const limite = Math.max(1, Math.min(+u.searchParams.get('limite') || 10, 30));
        const chats = (await client.getChats()).sort((a, b) => (b.timestamp || 0) - (a.timestamp || 0)).slice(0, limite);
        return json(res, 200, chats.map((c) => ({ id: idDe(c.id), nome: c.name || idDe(c.id), naoLidas: c.unreadCount || 0, ultima: c.lastMessage?.body || '' })));
      }
      if (req.method === 'GET' && u.pathname === '/mensagens') {
        const chat = await client.getChatById(u.searchParams.get('id'));
        const ms = await chat.fetchMessages({ limit: Math.max(1, Math.min(+u.searchParams.get('limite') || 15, 40)) });
        return json(res, 200, ms.map((m) => ({ quem: m.fromMe ? 'eu' : 'contato', texto: m.body || '[mídia]' })));
      }
      if (req.method === 'POST' && u.pathname === '/rascunho') {
        const { id, texto } = await corpo(req);
        rascunhos.set(id, texto);
        return json(res, 200, { ok: true });
      }
      if (req.method === 'POST' && u.pathname === '/enviar') {
        const { id, texto } = await corpo(req);
        if (!id || !texto) return json(res, 400, { erro: 'id e texto' });
        await client.sendMessage(id, String(texto).slice(0, 4000));
        rascunhos.delete(id);
        return json(res, 200, { ok: true });
      }
      return json(res, 404, { erro: 'rota' });
    } catch (e) {
      return json(res, 500, { erro: String(e.message || e) });
    }
  });
}

module.exports = { criarServidor, idDe };
