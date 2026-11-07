// node --test testes.js   (sem WhatsApp e sem internet)
const test = require('node:test');
const assert = require('node:assert/strict');
const N = require('./atendente-nucleo');
const { criarServidor } = require('./ponte-http');

test('partes, humano, repetição', () => {
  assert.deepEqual(N.partes('Oi!\n\nTudo bem?  \n'), ['Oi!', 'Tudo bem?']);
  assert.equal(N.ehHumano('Vou confirmar [HUMANO]'), true);
  assert.equal(N.limpar('Vou confirmar [HUMANO]'), 'Vou confirmar');
  assert.equal(N.semRepeticao('Qual seu CNPJ?', ['Qual seu CNPJ?'], 'outra'), 'outra');
  assert.equal(N.semRepeticao('nova', ['velha'], 'outra'), 'nova');
  assert.ok(N.pausaDigitando('x'.repeat(500)) <= 4000);
});

test('cérebro: cascata em 429 e fim de linha em [HUMANO]', async () => {
  const chamados = [];
  const fetchFn = async (_u, o) => { const m = JSON.parse(o.body).model; chamados.push(m); return m === 'a' ? { status: 429, ok: false } : { status: 200, ok: true, json: async () => ({ choices: [{ message: { content: 'Resposta' } }] }) }; };
  const r = await N.pensar({ prompt: 'p', historico: [], chave: 'k', fetchFn, modelos: ['a', 'b'] });
  assert.deepEqual(chamados, ['a', 'b']);
  assert.equal(r.texto, 'Resposta');
  const todos429 = await N.pensar({ prompt: 'p', historico: [], chave: 'k', fetchFn: async () => ({ status: 429, ok: false }), modelos: ['a'] });
  assert.ok(N.ehHumano(todos429.texto));
});

test('ponte: token, host, conversas, enviar', async () => {
  const enviados = [];
  const client = {
    getChats: async () => [{ id: { _serialized: '1@c.us' }, name: 'Marina', unreadCount: 2, timestamp: 5, lastMessage: { body: 'Oi' } }, { id: { $1: '2@c.us' }, name: 'Carlos', unreadCount: 0, timestamp: 9, lastMessage: { body: 'Valeu' } }],
    getChatById: async () => ({ fetchMessages: async () => [{ fromMe: false, body: 'Qual o prazo?' }, { fromMe: true, body: 'Sexta' }] }),
    sendMessage: async (id, t) => enviados.push([id, t]),
  };
  const s = criarServidor({ client, token: 'tok' });
  await new Promise((r) => s.listen(0, '127.0.0.1', r));
  const base = `http://127.0.0.1:${s.address().port}`;
  try {
    assert.equal((await fetch(base + '/conversas')).status, 401);
    const h = { 'x-token': 'tok' };
    const lista = await (await fetch(base + '/conversas', { headers: h })).json();
    assert.equal(lista[0].nome, 'Carlos'); assert.equal(lista[0].id, '2@c.us'); assert.equal(lista[1].naoLidas, 2);
    const ms = await (await fetch(base + '/mensagens?id=1@c.us', { headers: h })).json();
    assert.deepEqual(ms.map((m) => m.quem), ['contato', 'eu']);
    assert.equal((await fetch(base + '/enviar', { method: 'POST', headers: h, body: JSON.stringify({ id: '1@c.us' }) })).status, 400);
    assert.equal((await fetch(base + '/enviar', { method: 'POST', headers: h, body: JSON.stringify({ id: '1@c.us', texto: 'Oi' }) })).status, 200);
    assert.deepEqual(enviados, [['1@c.us', 'Oi']]);
  } finally { s.close(); }
});
