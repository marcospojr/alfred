// Peças do atendente que não dependem do WhatsApp (por isso são testáveis): humanizar, travar repetição, chamar o cérebro.
const MODELOS = (process.env.MODELOS || 'openai/gpt-oss-120b,openai/gpt-oss-20b').split(','); // confira a lista do dia (GET /openai/v1/models)

const partes = (texto) => texto.split(/\n+/).map((p) => p.trim()).filter(Boolean).slice(0, 4);
const ehHumano = (texto) => /\[HUMANO\]/i.test(texto);
const limpar = (texto) => texto.replace(/\[HUMANO\]/gi, '').trim();
// Instrução no prompt não impede o modelo de repetir; a trava tem que ficar no código.
const semRepeticao = (novo, ultimas, alternativa) => (ultimas.map((x) => x.trim()).includes(novo.trim()) ? alternativa : novo);
const pausaDigitando = (parte) => 1000 + Math.min(3000, parte.length * 30);

function montarPrompt(promptBase, negocio, agora = new Date()) {
  return promptBase.replace('{{data}}', agora.toLocaleString('pt-BR')).replace('{{base}}', negocio);
}

async function pensar({ prompt, historico, chave, fetchFn = fetch, modelos = MODELOS }) {
  for (const modelo of modelos) {
    const r = await fetchFn('https://api.groq.com/openai/v1/chat/completions', {
      method: 'POST', headers: { 'content-type': 'application/json', authorization: `Bearer ${chave}` },
      body: JSON.stringify({ model: modelo, temperature: 0.3, max_tokens: 400, reasoning_effort: 'low', messages: [{ role: 'system', content: prompt }, ...historico] }),
    });
    if (r.status === 429 || r.status === 404 || r.status === 400) continue; // cota estourou ou o modelo sumiu: tenta o próximo
    if (!r.ok) throw new Error('provedor ' + r.status);
    const j = await r.json();
    const texto = (j.choices?.[0]?.message?.content || '').trim();
    if (texto) return { texto, modelo };
  }
  return { texto: 'Já te respondo, só um instante. [HUMANO]', modelo: 'espera' };
}

module.exports = { partes, ehHumano, limpar, semRepeticao, pausaDigitando, montarPrompt, pensar };
