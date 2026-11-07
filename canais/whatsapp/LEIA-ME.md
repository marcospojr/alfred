# WhatsApp no Alfred

Dois modos, mesmo programa (`whatsapp.js`):

1. **Ponte (padrão):** o Alfred lê as suas conversas e **prepara** respostas. Enviar sempre pede o seu "sim". Não responde sozinho.
2. **Atendente:** responde clientes sozinho com cérebro gratuito (Groq) e registra tudo em `dados/atendimento.db`; o Alfred supervisiona e gera relatórios (`atendimento_relatorio`).

## Antes de ligar
- Use um **número dedicado**. Bibliotecas de WhatsApp Web não são oficiais: **o número pode ser banido**. Caminho oficial: API da Meta (conta comercial, modelos aprovados, custo por conversa).
- Node.js **22.13 ou mais novo** (recomendado: 24 LTS). `cd canais/whatsapp && npm install` (aceite baixar o Chromium do puppeteer).
- No `config.toml`: `[whatsapp] ativo = true`.

## Ponte
```
node whatsapp.js
```
O terminal desenha um **QR code**. No celular: WhatsApp > Aparelhos conectados > Conectar. A sessão fica em `dados/whatsapp-sessao`. Depois abra o Alfred e peça: "o que chegou no WhatsApp hoje?".

## Atendente
1. Copie `presets/atendente/negocio.exemplo.md` para `atendente/negocio.md` e preencha. Copie `presets/atendente/prompt.txt` para `atendente/prompt.txt` se quiser ajustar o tom.
2. Teste em simulação (não envia nada): `SIMULACAO=1 MODO=atendente ALFRED_CHAVE_GROQ=... node whatsapp.js`
3. Em produção o launcher lê a chave do cofre: `python -m alfred atendente` (ou `iniciar-atendente.sh` / `.bat`).
4. Defina `NUMERO_DONO=55DDDNUMERO@c.us` para receber o aviso quando um cliente precisar de uma pessoa.
5. Ative a rotina `presets/rotinas/relatorio-atendente.toml` para o relatório diário.

## Lições de quem já operou
- Prompt grande estoura a cota gratuita por minuto; mantenha a base enxuta.
- Instrução no prompt não impede repetição: a trava está no código (`semRepeticao`).
- Nunca rode duas cópias ao mesmo tempo (duas brigam pela sessão).
- Não instale num número em que pessoas já atendem à mão.
- Mac que dorme ou desliga derruba o atendente: para 24 h, use um servidor pequeno.
- Se a lib renomear campos (ex.: `id._serialized`), ajuste em `ponte-http.js` (`idDe`).

## Status de testes deste kit
Testado: lógica do atendente e a API local da ponte (`node --test testes.js`). **Não testado:** conexão real com o WhatsApp (precisa de QR e de um número).
