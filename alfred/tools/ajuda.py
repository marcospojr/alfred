"""Ajuda embutida: o Alfred lê os guias de criação (docs/) antes de montar automações, apps, conectores e MCPs."""
from pathlib import Path

from ..config import BASE
from ..gate import Risco
from . import Ferramenta, esquema, texto

MARCA = "<!--completo-->"
TEMAS = {"automacao": "AUTOMACOES.md", "app": "APPS.md", "conector": "CONECTORES.md", "mcp": "MCP.md", "claude": "CLAUDE-E-ALFRED.md"}


def criar(ctx):
    def ajuda(tema: str, completo: bool = False):
        arq = TEMAS.get(tema.lower())
        if not arq:
            return f"temas: {', '.join(TEMAS)}"
        texto_ = (BASE / "docs" / arq).read_text(encoding="utf-8")
        if not completo and MARCA in texto_:
            return texto_.split(MARCA)[0].strip()     # resumo para a IA (gasta pouco); completo=true traz o guia inteiro
        return texto_[:12000]

    return [Ferramenta("ajuda_criar", "Guia completo (formato, exemplos, regras de segurança) para criar automacao, app, conector, mcp ou claude. LEIA antes de criar.",
                       esquema({"tema": texto("automacao | app | conector | mcp | claude"), "completo": {"type": "boolean"}}, ["tema"]), Risco.VERDE, ajuda, lambda tema, completo=False: f"ler o guia '{tema}'")]
