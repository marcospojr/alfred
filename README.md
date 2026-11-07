# Alfred Kit

Base pronta para montar o seu assistente pessoal de IA no **Mac** ou no **Windows**. Não é só um prompt: é um programa que roda no seu computador, com cérebro intercambiável, memória, ferramentas que agem de verdade (arquivos, apps, agenda, e-mail, navegador, WhatsApp), um **portão de segurança** que pede o seu sim antes de qualquer ação com risco, tela de conversa com log ao vivo, voz, rotinas automáticas e um atendente opcional de WhatsApp para clientes.

> Feito para ser usado **junto com uma IA** (Claude, ChatGPT, Gemini...): entregue esta pasta e o arquivo `ALFRED-PARA-O-CLAUDE.md` e peça "monte o meu Alfred a partir do Alfred Kit". Ela já tem o chão pronto e só customiza.

## Instalar (5 minutos)

**Mac:** abra o Terminal na pasta e rode `./install.sh`. Depois dê dois cliques em `iniciar.command`.
**Windows:** abra o PowerShell na pasta e rode `.\install.ps1`. Depois dê dois cliques em `iniciar.bat`.

O instalador explica cada passo, usa o `uv` para instalar o Python certo só dentro desta pasta, e guarda a chave no cofre do sistema (Chaveiro no Mac, Gerenciador de Credenciais no Windows). **Nunca cole chave em arquivo ou em chat.**

Chave grátis: https://console.groq.com/keys (**Groq**, com Q). Para outro cérebro, mude `provedor` (e `modelo`) no `config.toml`: `openai`, `anthropic`, `gemini`, `xai`, `openrouter` ou `ollama` (local, sem chave). Rode `python -m alfred chave <nome>` para guardar a chave de cada um.

Conferir a instalação: `.venv/bin/python -m alfred testar` (Mac) ou `.venv\Scripts\python -m alfred testar` (Windows).

## O que ele faz

| Área | Ferramentas | Risco |
|---|---|---|
| Arquivos (só nas pastas que você liberar) | listar, ler, buscar, escrever, mover, **mover para a lixeira** | V / A |
| Computador | hora, info do sistema, abrir app, abrir link, área de transferência, captura de tela, **executar comando** (lista fechada) | V / A / R |
| Web | ler página, buscar na web (bloqueia endereços internos) | V |
| Memória | lembrar, buscar (sem acento), listar, esquecer | V / A |
| Agenda | ler `.ics` (Google/Outlook/Apple) ou Calendário do Mac; criar evento (abre o .ics para você confirmar) | V / A |
| E-mail (opcional) | listar (só leitura), **enviar** | V / R |
| WhatsApp (opcional) | listar e ler conversas, rascunho, **enviar**, relatório do atendente | V / A / R |
| Mouse e teclado (opcional) | clicar, digitar, atalhos | A |
| Navegador próprio (opcional) | abrir, ler, clicar, preencher, capturar (perfil separado do seu) | V / A |

**V** só lê, **A** muda algo reversível (confirma na 1ª vez), **R** apaga, envia para fora ou não tem volta (**sempre** confirma, com os valores reais na frase).

## Operador do computador: criar automações, apps, APIs e MCPs (o Alfred faz isso sozinho)
O Alfred não só executa: ele **constrói o que você precisa**, sempre com o seu "sim". Peça em português ("toda sexta às 17h me manda o resumo das vendas", "faz um painel de pedidos", "conecta a API do meu ERP", "conecta o servidor MCP do GitHub").

| Capacidade | Como funciona | Guia |
|---|---|---|
| **Automações** | arquivos em `automacoes/`; gatilhos: horário, intervalo, pasta, webhook, evento, manual; passos: ferramenta, cérebro, aviso, **chamar outra automação**, **emitir evento** (encadeamento); nascem desligadas; só ferramentas vermelhas listadas em `permite` rodam sozinhas | `docs/AUTOMACOES.md` |
| **Mini-apps** | telas HTML que ele cria e serve em `/apps/<nome>/`, com armazenamento próprio e token próprio (sem internet, sem poder de ação) | `docs/APPS.md` |
| **Conectores de API** | descreve uma API em JSON; a chave fica no cofre; leitura livre, ação com confirmação | `docs/CONECTORES.md` |
| **MCP** | conecta qualquer servidor MCP (GitHub, Notion, Google, bancos, navegador...); as ferramentas viram do Alfred, pelo portão | `docs/MCP.md` |
| **Claude e nuvem** | `python -m alfred mcp` deixa o Claude Desktop/Code pedir coisas ao Alfred; `delegar_claude_code` entrega programação pesada ao Claude Code; webhooks ativam automações de fora (n8n, Zapier, túnel privado) | `docs/CLAUDE-E-ALFRED.md` |

**Grupos de ferramentas:** para gastar poucos tokens, o Alfred começa só com o núcleo (arquivos, memória, hora, apps) e liga `web`, `comunicacao`, `criar`, `integracoes` ou `controle` quando o pedido precisa (`habilitar_grupo`). Com cérebro pago, ligue tudo em `grupos_sempre`. O botão **painel** na tela mostra automações (com "rodar agora"), apps, APIs e MCPs.

**Exemplos prontos:** `presets/automacoes/` (bom-dia no WhatsApp, PDF novo vira resumo, encadeamento por evento), `presets/conectores/` (ViaCEP e Open-Meteo funcionam sem chave).

## Segurança (o código impõe, não o prompt)
- Portão de risco (`alfred/gate.py`): a confirmação vem de **você** (botão na tela), nunca do modelo.
- Três modos: `observar` (só leitura), `supervisionado` (padrão), `liberado` (age sozinho só no amarelo).
- Arquivos só em `pastas` do `config.toml`; `.env`, chaves, `.ssh` e cofres são bloqueados; atalhos simbólicos não escapam.
- Conteúdo de fora (web, e-mail, WhatsApp, arquivos) chega marcado como **dado, não ordem** (defesa contra injeção de prompt).
- O servidor só aceita `127.0.0.1`, exige token e confere o `Host` (contra DNS rebinding).
- Botão **parar** interrompe o laço; teto de gasto diário; no máximo 8 passos por pedido; log de auditoria em `dados/auditoria.jsonl`.

## Telegram
Converse pelo celular (texto ou áudio), aprove ações com botões e receba as rotinas. Veja `docs/TELEGRAM.md`.

## Voz
- **Falar:** botão "voz" na tela usa a voz do navegador/sistema (grátis).
- **Ouvir:** botão do microfone grava no navegador e transcreve com a Groq (grátis, com limite; o áudio sai do computador). Para tudo local, troque por whisper.cpp (veja o manual).

## Rotinas (roda sozinho)
Arquivos `.toml` em `presets/rotinas/` ou `rotinas/`: `ativa = true`, hora, dias e o pedido. Rodam em modo `observar` (só leitura) e usam o **relógio de parede**: se o computador estava dormindo na hora, rodam quando ele acordar. Mantenha o Alfred aberto (ou instale como serviço: LaunchAgent no Mac, Agendador de Tarefas no Windows).

## WhatsApp
Veja `canais/whatsapp/LEIA-ME.md` (ponte para o Alfred ler e responder, e atendente automático de clientes com relatórios). **Número dedicado, e leia o aviso de banimento.**

## Estrutura
```
alfred/            núcleo: cerebro.py (provedores + laço), gate.py (portão), memoria.py, agente.py, servidor.py, rotinas.py, automacoes.py, apps.py, conectores.py, mcp_cliente.py, mcp_servidor.py
alfred/tools/      uma ferramenta por função; crie a sua copiando um módulo (Ferramenta + risco + frase)
alfred/web/        tela de conversa (um arquivo HTML)
canais/whatsapp/   ponte e atendente (Node.js)
presets/           perfis, habilidades, rotinas, automações, conectores e o atendente de exemplo
docs/              guias de criação (o Alfred lê com ajuda_criar)
CLAUDE.md          convenções para o Claude Code evoluir o kit
testes/            bateria de aceitação: python -m pytest testes -q
dados/             memória, auditoria, sessões (fora do git)
```

### Criar uma ferramenta nova
Copie `alfred/tools/memoria_ferr.py`, troque as funções, escolha o risco (V/A/R), escreva a `frase` que descreve a ação com os valores reais, e acrescente o nome do módulo em `MODULOS` (`alfred/tools/__init__.py`). Rode os testes.

## Status de testes (honesto)
- **Testado (Mac, Python 3.12):** automações (validação, encadeamento, permissões, gatilhos, webhook), mini-apps (tokens, CSP), conectores (chamadas reais ao ViaCEP e Open-Meteo), cliente MCP contra um servidor MCP oficial real (filesystem), servidor MCP do Alfred, grupos de ferramentas, portão, memória, sandbox de arquivos, laço do cérebro, adaptadores OpenAI-compatível e Anthropic (conversão de mensagens), servidor com confirmação pela tela, rotinas com sono do computador, leitor de agenda `.ics`, ponte e núcleo do atendente (`node --test`). Conversa real com ferramentas e confirmações usando a Groq.
- **Não testado:** Windows (código escrito para ele, sem rodar), conexão real do WhatsApp (precisa de QR e número), e-mail em servidor real, Calendário do Mac e voz pelo microfone, controle de mouse/teclado e navegador próprio.
- Cota gratuita da Groq: ~8 mil tokens por minuto por modelo; cada pedido com ferramentas gasta de 2 a 4 mil (mais ao criar coisas): para criar automações e apps com folga, use Gemini (camada gratuita maior), um provedor pago ou o modelo local. Em uso intenso, use um provedor pago ou o modelo local.

## Remover tudo
Feche o Alfred; apague esta pasta; remova a chave (`python -m alfred chave` guarda; para remover use o app Chaveiro/Gerenciador de Credenciais, entrada "alfred"); revogue a chave no painel do provedor; desconecte o WhatsApp em Aparelhos conectados.

IACOM · versão 1.0.0 · out/2026
