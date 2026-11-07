# RESUMO PARA A IA: criar mini-app
Ferramenta: app_criar(nome, titulo, html, descricao, arquivos). Abrir: app_abrir. Editar: app_atualizar. Endereço: http://127.0.0.1:PORTA/apps/<nome>/.
html = um index.html completo com <style> e <script> embutidos. SEM links externos (CDN, fontes, fetch para outros sites: a política de segurança bloqueia). arquivos opcional: {"app.js":"...","estilo.css":"..."}.
O servidor injeta window.ALFRED_APP: await ALFRED_APP.lerDados() / salvarDados(obj) (JSON até 1 MB) e await ALFRED_APP.perguntar("texto") (o Alfred responde só com leitura).
O app não tem o token principal: não aprova nada nem aciona ações. Escape texto em innerHTML (use textContent). Layout para celular (viewport, inputs >= 16px).
Passos: entender o que a pessoa quer ver; escrever index.html; app_criar; app_abrir; pedir teste; ajustar.
<!--completo-->
# Como criar aplicativos dentro do Alfred (mini-apps)

Um mini-app é uma tela (HTML/CSS/JS) que o Alfred cria para a pessoa e serve em `http://127.0.0.1:PORTA/apps/<nome>/`. Serve para painel de vendas, lista de tarefas, formulário de cadastro, calculadora do negócio, kanban, CRM simples, o que a pessoa imaginar.

Ferramentas: `app_criar`, `app_listar`, `app_ler`, `app_atualizar`, `app_excluir` (vai para `apps/_lixeira`), `app_abrir`.

## O que o app recebe pronto
O servidor injeta `window.ALFRED_APP` no `<head>` do `index.html`:
- `await ALFRED_APP.lerDados()` devolve o JSON guardado do app (um arquivo `dados.json`, até 1 MB).
- `await ALFRED_APP.salvarDados(objeto)` guarda.
- `await ALFRED_APP.perguntar("texto")` pergunta ao Alfred (ele responde com **ferramentas de leitura apenas**: agenda, arquivos, memória, conectores de leitura).

## Regras (o servidor impõe)
- **Sem internet no app:** a política de segurança (CSP) só deixa o app falar com o próprio Alfred (`connect-src 'self'`). Nada de CDN, fontes externas ou `fetch` para outros sites. Use CSS e JS puros e embutidos. Se o app precisa de dados da web, o Alfred busca (conector) e entrega ao app via `salvarDados`.
- **Token próprio:** o app tem um token que só abre os dados dele e a pergunta de leitura. Ele **não** recebe o token principal: não pode aprovar confirmações nem acionar ferramentas de ação.
- Nomes de arquivo: letras, números, ponto, hífen; extensões `.html .js .css .json .txt .svg .md`; até 400 mil caracteres cada.

## Receita
1. Entenda o que a pessoa quer ver e fazer. Desenhe a tela mentalmente em 1 minuto: cabeçalho, lista/tabela, formulário, botões.
2. Escreva um único `index.html` (use `<style>` e `<script>` embutidos; para apps grandes, passe `arquivos` com `app.js` e `estilo.css` e referencie-os por nome relativo).
3. Carregue os dados com `lerDados()` ao abrir e salve a cada mudança com `salvarDados()`.
4. Layout que funciona no celular (a pessoa pode abrir o endereço pela rede privada): `meta viewport`, fonte >= 16px em inputs, botões >= 44px.
5. Crie com `app_criar`, abra com `app_abrir` e peça à pessoa para testar. Ajuste com `app_atualizar`.

## Esqueleto mínimo
```html
<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Tarefas</title>
<style>body{font:16px system-ui;margin:0;padding:20px;background:#0b0b0b;color:#eee}input,button{font:inherit;padding:10px;border-radius:10px;border:1px solid #444;background:#1a1a1a;color:#eee}li{padding:8px 0}</style></head>
<body><h1>Tarefas</h1><input id="t" placeholder="Nova tarefa"><button id="b">Adicionar</button><ul id="l"></ul>
<script>
let d={itens:[]};
async function ini(){d=Object.assign({itens:[]},await ALFRED_APP.lerDados());desenhar()}
function desenhar(){l.innerHTML=d.itens.map((x,i)=>`<li><label><input type=checkbox ${x.ok?'checked':''} data-i=${i}> ${x.t.replace(/</g,'&lt;')}</label></li>`).join('')}
b.onclick=async()=>{if(!t.value)return;d.itens.push({t:t.value,ok:false});t.value='';desenhar();await ALFRED_APP.salvarDados(d)};
l.onchange=async e=>{d.itens[e.target.dataset.i].ok=e.target.checked;await ALFRED_APP.salvarDados(d)};
ini();
</script></body></html>
```
(Escape sempre o texto que vai para `innerHTML`. Use `textContent` quando possível.)

## Conectar apps que você já tem
- App web que já roda (localhost ou na internet): crie um **conector** (`ajuda_criar('conector')`) para a API dele, ou apenas `app_criar` uma tela que mostre o que o Alfred busca por conector.
- Programa de linha de comando seu: liste-o em `comandos_permitidos` do `config.toml` (a pessoa edita) e use `executar_comando` (vermelho, sempre confirma).
- Qualquer ferramenta que tenha servidor MCP: `ajuda_criar('mcp')`.
