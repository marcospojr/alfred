# Progresso do Alfred

## Fase 0 · Preparação — 30/out/2026 · PC servidor da Be Aesthetic (Windows 11)

**Pronto e testado no próprio PC:**
- Kit em `Documentos\alfred\alfred-kit`, Python 3.12 só na pasta `.venv` (via uv).
- Cérebro: Groq (grátis), modelo `openai/gpt-oss-120b` (reserva `openai/gpt-oss-20b`). Chamada real `python -m alfred oi` respondeu "Oi!" (97 tokens de entrada, 42 de saída, US$ 0).
- Chave da Groq no Gerenciador de Credenciais do Windows (entrada "alfred"), nunca em arquivo.
- Bateria de testes no Windows: 62 passaram (antes da última correção); depois dela, 64 passam no ambiente do Claude.

**Corrigido para o Windows nesta fase:**
- `echo`/`dir` (comandos internos do cmd) agora rodam via `cmd /d /c`; `&`, `^`, `%` e quebra de linha bloqueados (encadeamento do cmd).
- Leitura/gravação com UTF-8 explícito (rotinas e testes).
- `python -m alfred chave` recusa chave colada errada (Ctrl+V no PowerShell gravava só o atalho) e ganhou `--colar` (lê a área de transferência e limpa depois).
- Novo `python -m alfred oi` com diagnóstico (formato da chave sem mostrá-la, lista de modelos da conta).

**Confirmado pelo Marcos em 31/out/2026:**
- Bateria de testes no Windows depois das correções: passou (1 aviso sobre httpx2, sem efeito).
- Energia: `powercfg` sem dormir, sem hibernar e monitor sempre ligado; BIOS com "Restore on AC Power Loss" = Power On.
- Token do bot do Telegram guardado no cofre (ainda não testado com o bot de verdade).

**Fase 0: portão passou em 31/out/2026.**

**Pendente:**
- Depois de uma queda de energia, o Windows para na tela de login e o Alfred não abre sozinho: resolver na Fase 8 (início automático).
- git não configurado (opcional).
- Trocar para Claude por API (US$ 5/mês) quando decidir: `provedor = "anthropic"`, `modelo = "claude-sonnet-5-5"` e `python -m alfred chave anthropic --colar`.

**Como revogar:** chave da Groq em console.groq.com/keys (apagar). Remover do PC: Gerenciador de Credenciais → Credenciais do Windows → "alfred".

**Custo medido:** US$ 0 (Groq gratuita).

## Fase 1 · Cérebro por texto — 03/nov/2026
- Conversa pela tela funcionou (Groq); custo aparece por resposta (US$ 0).
- Sem internet: teste automático (erro claro "sem conexão com o cérebro", 3 tentativas, volta a responder). Teste real com cabo desligado fica para quando o Marcos estiver na loja.
- Bateria no Windows: 65 passed. **Portão passou.**

## Telegram (adiantado da Fase 6) — 03/nov/2026
- Bot ligado; só atende o dono_id do Marcos.
- Testado de verdade: "que horas são?" respondido; pedido de criar teste.txt mostrou os botões, Marcos apertou Não e o log registrou "recusado" (06:23:59). **Aprovado.**
- Janela preta agora mostra o estado do Telegram; `testar` confere o bot com getMe.

**Pendentes novos:**

## Contador da cota + correções — 03/nov/2026
- Painel e /cota no Telegram: uso do dia por modelo (Groq: cabeçalhos x-ratelimit + contagem local; Claude Code: chamadas e custo equivalente).
- Corrigido: limite_diario_usd do config.toml não era aplicado; testes gravavam no log real; testes agora usam dados/tmp-testes (pytest.ini).
- Teste de atalho no Windows usa junção (mklink /J), que não pede administrador. Bateria no Windows: 82 passed.

## Claude Code — 03/nov/2026
- Instalado por winget (2.1.302), login na assinatura do Marcos.
- Ferramentas claude_consultar (só lê/pesquisa) e claude_tarefa (cria/edita arquivos). Rodam com --restricted (sem comandos, presas à pasta Alfred-Arquivos), sem chave de API, limite 10/dia, nunca em automação/rotina.
- Decisão do Marcos: consulta sem pedir o sim (consulta_sem_perguntar = true), só quando é ele pedindo (tela/Telegram); tarefa sempre pergunta.
- Testado de verdade: consulta pelo Telegram respondeu em ~1,5 min; aviso "Consultando o Claude…" no Telegram.

## Agenda do Google (leitura) — 03/nov/2026
- Endereço secreto iCal no cofre ("agenda"); cópia local por 10 min e reserva sem internet; eventos repetidos, dia inteiro, exceções e cancelados.
- Testado de verdade: agenda_hoje leu a agenda do Marcos (16:16:55). Falta o Marcos confirmar que bate com o Google.
- Criar eventos: pendente (precisa de permissão de escrita no Google).

## E-mails (4 contas) — 04/nov/2026
- marcospojr13, marcospojr, beaesthetic-gmail (senhas de app) e contato@ (Hostinger, senha da caixa). Login das 4 testado com `testar`.
- Leitura sem marcar como lido; "todas" = 5 de cada; paginação ("os próximos"); rascunho em vez de envio; envio desligado.
- Leitura de e-mail e agenda ficam sempre ligadas (a Groq não ligava o grupo sozinha). Testado de verdade pelo Telegram.

## Checklist + rotinas — 04/nov/2026
- Tarefas em dados/tarefas.db; /tarefas no Telegram; resumo_do_dia junta agenda + checklist + e-mails numa chamada.
- Rotinas: bom-dia 07:30 e fechamento 18:00, seg a sáb, em modo observar. Bom-dia recebido de verdade.

## Serviço escondido — 04/nov/2026
- Windows sem senha: já entra sozinho (sem Autologon). Atalho na Inicialização abre `pythonw -m alfred servico` (vigia).
- Vigia: uma cópia só, reabre se cair (5 s → 60 s), /reiniciar pelo Telegram, log em dados/alfred.log.
- Testado de verdade: /reiniciar e reinício do PC (Alfred voltou sozinho).
- Decisão: bloqueio de tela dispensado por enquanto (só o funcionário tem acesso físico).

**Para depois (pedido do Marcos):**
- Juntar as agendas das outras contas (evento no marcospojr não apareceu: hoje só lê a agenda do marcospojr13).
- Descanso de tela das promoções em 20–30 s (ou app de exibição).
- Área de Trabalho Remota pelo Tailscale exige senha no Windows (aí usar Autologon).
