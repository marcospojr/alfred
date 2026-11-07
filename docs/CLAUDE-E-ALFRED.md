# RESUMO PARA A IA: Alfred e Claude
1) Claude pede, Alfred executa: `python -m alfred mcp` expõe alfred_pedir. 2) Alfred pede ajuda ao Claude Code: claude_consultar e claude_tarefa (vermelhas, precisam do comando `claude`; nunca em automação). 3) Claude Code abre a pasta do kit e evolui o Alfred (leia CLAUDE.md). Ativar de fora: webhook (POST /api/webhook/<nome> com x-webhook-secret) por túnel privado.
Só a pessoa aprova ações vermelhas (tela do Alfred ou "permite" aprovado por escrito).
<!--completo-->
# Alfred + Claude: quem faz o quê

O Alfred é o **operador do computador**: está sempre ligado, tem memória, ferramentas, automações e o portão de segurança. O Claude (Desktop, Code ou o app) é o **pensador/construtor**: ótimo para planejar, escrever código e conversar. Os dois se ajudam de três jeitos.

## 1. Claude pede, o Alfred executa (Alfred como servidor MCP)
`python -m alfred mcp` expõe `alfred_pedir`. No Claude: "peça ao Alfred para organizar a minha pasta Downloads". O Alfred faz com o portão dele; confirmações aparecem na tela do Alfred. Configuração em `docs/MCP.md`.

## 2. Alfred delega programação ao Claude Code
Com o Claude Code instalado (comando `claude` no PATH), o Alfred ganha `claude_consultar(pergunta, pasta)` (só lê e pesquisa) e `claude_tarefa(tarefa, pasta)` (cria e edita arquivos). Ambas vermelhas (sempre confirmam), rodam com `--restricted` (sem comandos, presas à pasta), na assinatura (sem chave de API), com limite diário em `[claude_code]` e contador no painel. Nunca em automação ou rotina.

## 3. Claude Code abre esta pasta e evolui o Alfred
Abra `alfred-kit` no Claude Code. O arquivo `CLAUDE.md` da pasta ensina as convenções: criar ferramenta nova, escrever teste, nunca mexer no portão sem teste, nunca pôr chave em arquivo. Peça: "adicione uma ferramenta que consulta o meu ERP" e ele escreve a ferramenta + teste.

## Ativar de fora (nuvem)
- **Webhook:** qualquer serviço (Claude agendado, n8n, Zapier, Make) chama `POST /api/webhook/<nome>` com `x-webhook-secret`: dispara só a automação ligada com aquele gatilho. Exponha por Tailscale Funnel ou cloudflared; nunca abra a porta do roteador.
- **Claude no celular:** com o túnel privado, o Claude (ou um atalho) chama o webhook; o Alfred age no computador de casa/escritório.
- **Servidor 24h:** para o Alfred nunca dormir, rode num computador sempre ligado ou numa VPS pequena (o controle de mouse/teclado só faz sentido em máquina com tela).

## Regra de ouro
Quem decide o que é arriscado é o portão do Alfred, não o Claude. Nenhum cliente MCP, app ou webhook consegue aprovar uma ação vermelha: só a pessoa, na tela do Alfred (ou o `permite` aprovado por escrito em uma automação).
