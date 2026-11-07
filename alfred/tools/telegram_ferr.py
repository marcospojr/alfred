"""Telegram: mandar um aviso para VOCÊ (o dono). Não envia para mais ninguém, por isso é verde."""
from ..gate import Risco
from . import Ferramenta, esquema, texto


def criar(ctx):
    if not ctx.cfg.get("telegram", {}).get("ativo"):
        return []

    def avisar(texto: str):
        canal = ctx.telegram
        if not canal:
            raise RuntimeError("o canal do Telegram não está ligado (confira o token e o dono_id)")
        if not canal.avisar(texto):
            raise RuntimeError("não consegui mandar pelo Telegram (veja o log)")
        return "aviso enviado para você no Telegram"

    return [
        Ferramenta("telegram_avisar", "Manda uma mensagem para a própria pessoa (dona do Alfred) no Telegram. Use para avisos, resumos e lembretes.",
                   esquema({"texto": texto("mensagem, em texto simples")}, ["texto"]), Risco.VERDE, avisar,
                   lambda texto: f"avisar você no Telegram: {texto[:120]}"),
    ]
