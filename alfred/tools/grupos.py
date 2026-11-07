"""habilitar_grupo: liga famílias de ferramentas só quando o pedido precisa (gasta menos tokens por chamada)."""
from ..gate import Risco
from . import GRUPOS, Ferramenta, esquema, texto


def criar(ctx):
    def habilitar(grupo: str):
        if grupo not in GRUPOS or grupo == "nucleo":
            return "grupos: " + "; ".join(f"{k} = {v}" for k, v in GRUPOS.items() if k != "nucleo")
        ctx.agente.ativos.add(grupo)
        return f"grupo '{grupo}' ligado. Ferramentas novas: " + ", ".join(n for n in ctx.agente.registro.por_nome if ctx.agente.registro.grupo(n) == grupo)[:700]

    return [Ferramenta("habilitar_grupo", "Liga um grupo de ferramentas (web, comunicacao, criar, integracoes, controle). Sem argumento válido, lista os grupos.",
                       esquema({"grupo": texto("web | comunicacao | criar | integracoes | controle")}, ["grupo"]), Risco.VERDE, habilitar, lambda grupo: f"ligar o grupo de ferramentas {grupo}")]
