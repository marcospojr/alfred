"""Sistema: hora, apps, links, área de transferência, captura de tela, comandos de uma lista fechada. Mac e Windows."""
import platform
import re
import shlex
import shutil
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

from ..config import DADOS
from ..gate import Risco
from . import Ferramenta, esquema, texto

MAC, WIN = sys.platform == "darwin", sys.platform.startswith("win")
FLAGS = subprocess.CREATE_NO_WINDOW if WIN else 0
# No Windows, estes comandos não são programas: existem só dentro do cmd. Rodam via "cmd /d /c", com a mesma trava de encadeamento.
EMBUTIDOS_CMD = {"echo", "dir", "ver", "vol"}   # "type" fica de fora: leria arquivos fora das pastas permitidas
# Sinais que encadeiam, redirecionam ou expandem no sh ou no cmd do Windows (& sozinho, ^ e % são do cmd).
PROIBIDOS = (";", "&", "|", ">", "<", "`", "$(", "^", "%", "\n", "\r")


def _rodar(args: list[str], timeout: int = 20, **kw) -> str:
    r = subprocess.run(args, capture_output=True, text=True, errors="replace", timeout=timeout, creationflags=FLAGS, **kw)
    saida = (r.stdout or "") + (("\n" + r.stderr) if r.stderr.strip() else "")
    if r.returncode != 0:
        raise RuntimeError(f"saiu com código {r.returncode}: {saida.strip()[:500]}")
    return saida.strip()


def criar(ctx):
    cfg = ctx.cfg

    def info_sistema():
        total, usado, livre = shutil.disk_usage(Path.home())
        return (f"sistema: {platform.system()} {platform.release()} ({platform.machine()})\ncomputador: {platform.node()}\n"
                f"python: {platform.python_version()}\ndisco livre: {livre // 2**30} GB de {total // 2**30} GB")

    def hora_atual():
        return time.strftime("%A, %d/%m/%Y %H:%M:%S (hora local)")

    def abrir_app(nome: str):
        if not re.fullmatch(r"[\w .\-+()]{1,60}", nome):
            raise ValueError("nome de aplicativo inválido (sem caminhos nem símbolos)")
        if MAC:
            _rodar(["open", "-a", nome])
        elif WIN:
            _rodar(["cmd", "/c", "start", "", nome])
        else:
            _rodar(["gtk-launch", nome])
        return f"abri {nome}"

    def abrir_url(url: str):
        if not re.match(r"https?://", url):
            raise ValueError("só links http(s)")
        webbrowser.open(url)
        return f"abri {url}"

    def area_ler():
        if MAC:
            return _rodar(["pbpaste"])
        if WIN:
            return _rodar(["powershell", "-NoProfile", "-Command", "Get-Clipboard"])
        return _rodar(["xclip", "-selection", "clipboard", "-o"])

    def area_escrever(texto: str):
        if MAC:
            subprocess.run(["pbcopy"], input=texto, text=True, check=True)
        elif WIN:
            subprocess.run(["clip"], input=texto, text=True, check=True, creationflags=FLAGS)
        else:
            subprocess.run(["xclip", "-selection", "clipboard"], input=texto, text=True, check=True)
        return f"copiei {len(texto)} caracteres"

    def executar_comando(comando: str):
        argv = shlex.split(comando, posix=not WIN)
        if not argv:
            raise ValueError("comando vazio")
        base = Path(argv[0]).name.lower().removesuffix(".exe")
        if base not in {c.lower() for c in cfg["comandos_permitidos"]}:
            raise PermissionError(f"'{base}' não está em comandos_permitidos do config.toml")
        if any(c in comando for c in PROIBIDOS):
            raise PermissionError("encadeamento e redirecionamento não são permitidos")
        if WIN and base in EMBUTIDOS_CMD:
            argv = ["cmd", "/d", "/c", *argv]
        return _rodar(argv, timeout=30, cwd=str(Path(cfg["pastas"][0]).expanduser()))[:4000]

    def captura_de_tela():
        pasta = DADOS / "capturas"
        pasta.mkdir(exist_ok=True)
        destino = pasta / time.strftime("tela-%Y%m%d-%H%M%S.png")
        if MAC:
            _rodar(["screencapture", "-x", str(destino)])
        else:
            from PIL import ImageGrab
            ImageGrab.grab().save(destino)
        return f"salvei em {destino}"

    return [
        Ferramenta("info_sistema", "Informações do computador: sistema, disco livre.", esquema(), Risco.VERDE, info_sistema, lambda: "ler informações do sistema"),
        Ferramenta("hora_atual", "Data e hora local de agora.", esquema(), Risco.VERDE, hora_atual, lambda: "ver a hora"),
        Ferramenta("abrir_app", "Abre um aplicativo pelo nome .", esquema({"nome": texto("nome do aplicativo")}, ["nome"]), Risco.AMARELO, abrir_app, lambda nome: f"abrir o aplicativo {nome}"),
        Ferramenta("abrir_url", "Abre um link http(s) no navegador padrão.", esquema({"url": texto("endereço completo")}, ["url"]), Risco.AMARELO, abrir_url, lambda url: f"abrir o link {url}"),
        Ferramenta("area_transferencia_ler", "Lê o texto copiado pela pessoa (Ctrl+C).", esquema(), Risco.VERDE, area_ler, lambda: "ler a área de transferência", externo=True),
        Ferramenta("area_transferencia_escrever", "Copia um texto para a área de transferência.", esquema({"texto": texto("texto a copiar")}, ["texto"]), Risco.AMARELO, area_escrever, lambda texto: f"copiar {len(texto)} caracteres para a área de transferência"),
        Ferramenta("executar_comando", "Roda um comando de uma lista fechada (config.toml), sem encadear.", esquema({"comando": texto("comando completo")}, ["comando"]), Risco.VERMELHO, executar_comando, lambda comando: f"EXECUTAR no computador: {comando}"),
        Ferramenta("captura_de_tela", "Salva uma foto da tela em dados/capturas.", esquema(), Risco.AMARELO, captura_de_tela, lambda: "tirar uma captura da tela"),
    ]
