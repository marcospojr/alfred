"""Ferramentas para o Alfred criar e manter mini-apps (telas) para você."""
import json
import webbrowser

from ..apps import ErroApp, GerenteApps, validar_novo
from ..gate import Risco
from . import Ferramenta, esquema, texto


def criar(ctx):
    def g() -> GerenteApps:
        if ctx.apps is None:
            raise RuntimeError("apps indisponíveis (o servidor ainda não iniciou)")
        return ctx.apps

    def _arquivos(arquivos):
        if not arquivos:
            return None
        a = json.loads(arquivos) if isinstance(arquivos, str) else arquivos
        if not isinstance(a, dict):
            raise ErroApp("'arquivos' deve ser um objeto {nome: conteudo}")
        return a

    def criar_app(nome: str, titulo: str, html: str, descricao: str = "", arquivos=None):
        g().criar(nome, titulo, html, descricao, _arquivos(arquivos))
        return f"app '{nome}' criado. Para abrir: app_abrir. Endereço: http://127.0.0.1:{ctx.cfg['porta']}/apps/{nome}/"

    def listar():
        return "\n".join(f"{a['nome']}: {a['titulo']} - {a['descricao']}" for a in g().listar()) or "nenhum app ainda"

    def ler(nome: str):
        return g().ler(nome)

    def atualizar(nome: str, html: str, arquivos=None):
        g().atualizar(nome, html, _arquivos(arquivos))
        return f"app '{nome}' atualizado"

    def excluir(nome: str):
        g().excluir(nome)
        return f"app '{nome}' movido para apps/_lixeira"

    def abrir(nome: str):
        g()._dir(nome)
        webbrowser.open(f"http://127.0.0.1:{ctx.cfg['porta']}/apps/{nome}/")
        return f"abri o app {nome}"

    N = {"nome": texto("nome do app: minúsculas, números, hífen ou _")}
    return [
        Ferramenta("app_criar", "Cria um mini-app (HTML/JS/CSS) servido localmente. Leia antes: ajuda_criar('app'). Use window.ALFRED_APP.lerDados/salvarDados para guardar dados.",
                   esquema({**N, "titulo": texto("título"), "html": texto("conteúdo de index.html (sem links externos)"), "descricao": texto("para que serve"), "arquivos": {"type": "object", "description": "opcional: {\"app.js\": \"...\", \"estilo.css\": \"...\"}"}}, ["nome", "titulo", "html"]), Risco.AMARELO,
                   criar_app, lambda nome, titulo, html, descricao="", arquivos=None: f"CRIAR o app '{nome}' ({titulo}), {len(html)} caracteres de HTML. Ele roda só neste computador e só guarda dados dele mesmo",
                   validar=lambda nome, titulo, html, descricao="", arquivos=None: validar_novo(nome, titulo, html, _arquivos(arquivos))),
        Ferramenta("app_listar", "Lista os mini-apps.", esquema(), Risco.VERDE, listar, lambda: "listar apps"),
        Ferramenta("app_ler", "Lê o HTML de um mini-app.", esquema(N, ["nome"]), Risco.VERDE, ler, lambda nome: f"ler o app {nome}"),
        Ferramenta("app_atualizar", "Troca o HTML (e arquivos) de um mini-app existente.", esquema({**N, "html": texto("novo index.html"), "arquivos": {"type": "object", "description": "opcional: arquivos extras"}}, ["nome", "html"]), Risco.AMARELO,
                   atualizar, lambda nome, html, arquivos=None: f"ATUALIZAR o app '{nome}' ({len(html)} caracteres)"),
        Ferramenta("app_excluir", "Move um mini-app para a lixeira de apps.", esquema(N, ["nome"]), Risco.AMARELO, excluir, lambda nome: f"mover o app {nome} para a lixeira"),
        Ferramenta("app_abrir", "Abre o mini-app no navegador.", esquema(N, ["nome"]), Risco.AMARELO, abrir, lambda nome: f"abrir o app {nome} no navegador"),
    ]
