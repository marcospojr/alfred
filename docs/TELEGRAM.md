# Telegram no Alfred

Você conversa com o Alfred pelo app do Telegram (texto ou áudio), aprova ações com botões **Sim / Não** e recebe as rotinas (bom-dia, resumos) como mensagem. É a API oficial do Telegram: sem risco de banimento, sem abrir porta no roteador.

## Ligar (10 minutos)
1. No Telegram, abra o **@BotFather** → `/newbot` → escolha um nome (ex.: "Alfred do Marcos") e um usuário terminado em `bot`. Ele te dá um **token** (algo como `123456:ABC...`). Não mande esse token para ninguém.
2. No PC do Alfred: `python -m alfred chave telegram` e cole o token (não aparece na tela).
3. Opcional, para áudio: crie uma chave gratuita em console.groq.com e rode `python -m alfred chave groq`.
4. No `config.toml`, seção `[telegram]`: `ativo = true`. Reinicie o Alfred.
5. Mande "oi" para o seu bot. Ele responde com o **seu ID**. Coloque `dono_id = SEU_ID` no `config.toml` e reinicie.
6. `python -m alfred testar` confere tudo.

## Usar
- Texto ou áudio: pede como pediria na tela.
- Ação amarela (dá para desfazer): botões **Sim / Sempre (nesta sessão) / Não**. Vermelha (sem volta): **Sim / Não**, sempre.
- Sem resposta em 3 minutos = não faz.
- `/parar` interrompe o que estiver em andamento.
- Rotinas ativas mandam o resultado para cá (`avisar_rotinas = true`; por rotina, `telegram = false` desliga).
- Ferramenta `telegram_avisar`: o Alfred (e as automações) podem te mandar um aviso. Só manda para você.

## Segurança
- Só o `dono_id` é atendido. Mensagens e cliques de outras pessoas são ignorados e ficam em `dados/auditoria.jsonl`.
- Enquanto `dono_id` estiver vazio, o bot só informa o ID de quem escreve. Não faz mais nada.
- Áudio: com a chave da Groq, o áudio sai do computador para ser transcrito. Para tudo local, troque por whisper.cpp (Fase 5).

## Status de testes
Testado (`python -m pytest testes -q`): dono x estranho, texto, áudio, botões de confirmação, /parar, rotina chegando no Telegram, montagem das URLs da API. **Não testado:** conversa com um bot real (precisa do token).
