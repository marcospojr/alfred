"""Navegador próprio do assistente (opcional: pip install playwright; playwright install chromium). Perfil separado, nunca o da pessoa."""
import threading

from playwright.sync_api import sync_playwright  # ImportError => módulo desligado

from ..config import DADOS
from ..gate import Risco
from . import Ferramenta, esquema, texto
from .web import url_publica

_estado = {"pw": None, "ctx": None, "pagina": None}
_trava = threading.RLock()


def _pagina():
    with _trava:
        if _estado["pagina"] is None or _estado["pagina"].is_closed():
            if _estado["pw"] is None:
                _estado["pw"] = sync_playwright().start()
                _estado["ctx"] = _estado["pw"].chromium.launch_persistent_context(str(DADOS / "navegador-perfil"), headless=False)
            ctx = _estado["ctx"]
            _estado["pagina"] = ctx.pages[0] if ctx.pages else ctx.new_page()
        return _estado["pagina"]


def criar(ctx):
    def navegar(url: str):
        url_publica(url)
        p = _pagina()
        p.goto(url, wait_until="domcontentloaded", timeout=30000)
        return f"abri {p.url} (título: {p.title()})"

    def ler():
        return _pagina().inner_text("body")[:8000]

    def clicar(seletor: str):
        _pagina().click(seletor, timeout=8000)
        return f"cliquei em {seletor}"

    def preencher(seletor: str, valor: str):
        _pagina().fill(seletor, valor, timeout=8000)
        return f"preenchi {seletor}"

    def capturar():
        destino = DADOS / "capturas" / "navegador.png"
        destino.parent.mkdir(exist_ok=True)
        _pagina().screenshot(path=str(destino))
        return f"salvei em {destino}"

    return [
        Ferramenta("navegador_abrir", "Abre uma página pública no navegador do assistente.", esquema({"url": texto("endereço completo")}, ["url"]), Risco.AMARELO, navegar, lambda url: f"abrir no navegador do assistente: {url}"),
        Ferramenta("navegador_ler", "Texto da página aberta no navegador do assistente.", esquema(), Risco.VERDE, ler, lambda: "ler a página aberta", externo=True),
        Ferramenta("navegador_clicar", "Clica num elemento (seletor CSS ou texto).", esquema({"seletor": texto("seletor Playwright")}, ["seletor"]), Risco.AMARELO, clicar, lambda seletor: f"clicar em {seletor} no navegador"),
        Ferramenta("navegador_preencher", "Preenche um campo de formulário.", esquema({"seletor": texto("seletor"), "valor": texto("valor")}, ["seletor", "valor"]), Risco.AMARELO, preencher, lambda seletor, valor: f"preencher {seletor} com \"{valor[:80]}\""),
        Ferramenta("navegador_capturar", "Foto da página aberta.", esquema(), Risco.VERDE, capturar, lambda: "capturar a página"),
    ]
