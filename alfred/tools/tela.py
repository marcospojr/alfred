"""Controle de mouse e teclado (opcional: pip install pyautogui). Tudo pede confirmação. Mover o mouse até o canto superior esquerdo aborta."""
import pyautogui  # ImportError => módulo desligado

from ..gate import Risco
from . import Ferramenta, esquema, inteiro, texto

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.15


def criar(ctx):
    def tamanho():
        w, h = pyautogui.size()
        x, y = pyautogui.position()
        return f"tela {w}x{h}; mouse em ({x},{y})"

    def clicar(x: int, y: int):
        w, h = pyautogui.size()
        if not (0 <= x < w and 0 <= y < h):
            raise ValueError("fora da tela")
        pyautogui.click(x, y)
        return f"cliquei em ({x},{y})"

    def digitar(conteudo: str):
        if not conteudo.isascii():
            raise ValueError("texto com acento ou símbolo: copie com area_transferencia_escrever e use o atalho de colar (ctrl+v ou command+v)")
        pyautogui.write(conteudo, interval=0.02)
        return f"digitei {len(conteudo)} caracteres"

    def atalho(teclas: str):
        pyautogui.hotkey(*[t.strip() for t in teclas.split("+")])
        return f"apertei {teclas}"

    return [
        Ferramenta("tela_info", "Tamanho da tela e posição do mouse.", esquema(), Risco.VERDE, tamanho, lambda: "ver tamanho da tela"),
        Ferramenta("clicar", "Clica numa posição da tela (x, y em pixels).", esquema({"x": inteiro("pixel x"), "y": inteiro("pixel y")}, ["x", "y"]), Risco.AMARELO, clicar, lambda x, y: f"clicar na tela em ({x},{y})"),
        Ferramenta("digitar", "Digita um texto onde o cursor estiver.", esquema({"conteudo": texto("texto")}, ["conteudo"]), Risco.AMARELO, digitar, lambda conteudo: f"digitar na tela: \"{conteudo[:120]}\""),
        Ferramenta("atalho", "Aperta um atalho de teclado, ex.: ctrl+c, command+tab.", esquema({"teclas": texto("teclas separadas por +")}, ["teclas"]), Risco.AMARELO, atalho, lambda teclas: f"apertar o atalho {teclas}"),
    ]
