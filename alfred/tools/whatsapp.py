"""WhatsApp pela ponte local (canais/whatsapp/whatsapp.js) + relatório do atendente."""
import sqlite3

import httpx

from ..config import DADOS
from ..gate import Risco
from . import Ferramenta, esquema, inteiro, texto


def _token() -> str:
    p = DADOS / "ponte.token"
    if not p.exists():
        raise RuntimeError("ponte do WhatsApp não configurada (rode o instalador ou veja canais/whatsapp/LEIA-ME.md)")
    return p.read_text().strip()


def criar(ctx):
    cfg = ctx.cfg["whatsapp"]
    if not cfg.get("ativo"):
        return []
    base = f"http://127.0.0.1:{cfg['porta']}"

    def chamar(metodo: str, caminho: str, **kw):
        try:
            r = httpx.request(metodo, base + caminho, headers={"x-token": _token()}, timeout=20, **kw)
        except httpx.ConnectError:
            raise RuntimeError("a ponte do WhatsApp não está rodando (node canais/whatsapp/whatsapp.js)")
        r.raise_for_status()
        return r.json()

    def conversas(limite: int = 10):
        return "\n".join(f"{c['id']} | {c['nome']} | não lidas: {c['naoLidas']} | última: {c['ultima'][:80]}" for c in chamar("GET", f"/conversas?limite={max(1, min(limite, 30))}")) or "nenhuma conversa"

    def ler(id: str, limite: int = 15):
        return "\n".join(f"[{m['quem']}] {m['texto']}" for m in chamar("GET", "/mensagens", params={"id": id, "limite": max(1, min(limite, 40))})) or "sem mensagens"

    def rascunho(id: str, texto: str):
        chamar("POST", "/rascunho", json={"id": id, "texto": texto})
        return "rascunho guardado (não enviado)"

    def enviar(id: str, texto: str):
        chamar("POST", "/enviar", json={"id": id, "texto": texto})
        return "mensagem enviada"

    def relatorio(dias: int = 1):
        db = DADOS / "atendimento.db"
        if not db.exists():
            return "ainda não há atendimentos registrados"
        con = sqlite3.connect(db)
        d = f"-{max(1, min(dias, 30))} day"
        n = con.execute("SELECT COUNT(DISTINCT conversa), SUM(quem='atendente'), COUNT(DISTINCT CASE WHEN humano=1 THEN conversa END), "
                        "ROUND(AVG(CASE WHEN quem='atendente' THEN ms END)/1000.0,1) FROM mensagens WHERE quando >= datetime('now', ?, 'localtime')", (d,)).fetchone()
        top = con.execute("SELECT texto, COUNT(*) v FROM mensagens WHERE quem='cliente' AND quando >= datetime('now', ?, 'localtime') GROUP BY texto ORDER BY v DESC LIMIT 5", (d,)).fetchall()
        chamados = con.execute("SELECT conversa, texto FROM mensagens WHERE humano=1 AND quando >= datetime('now', ?, 'localtime') ORDER BY id DESC LIMIT 5", (d,)).fetchall()
        return (f"conversas: {n[0]} | respostas: {n[1] or 0} | passadas para humano: {n[2]} | tempo médio: {n[3]} s\n"
                "perguntas mais frequentes:\n" + "\n".join(f"- {t} ({v}x)" for t, v in top) + "\nchamados humanos recentes:\n" + "\n".join(f"- {c}: {t[:100]}" for c, t in chamados))

    return [
        Ferramenta("whatsapp_conversas", "Lista conversas recentes do WhatsApp (ponte local).", esquema({"limite": inteiro("1 a 30")}), Risco.VERDE, conversas, lambda limite=10: "listar conversas do WhatsApp", externo=True),
        Ferramenta("whatsapp_ler", "Lê as últimas mensagens de uma conversa.", esquema({"id": texto("id da conversa (de whatsapp_conversas)"), "limite": inteiro("1 a 40")}, ["id"]), Risco.VERDE, ler, lambda id, limite=15: f"ler a conversa {id}", externo=True),
        Ferramenta("whatsapp_rascunho", "Guarda um rascunho de resposta (não envia).", esquema({"id": texto("id da conversa"), "texto": texto("rascunho")}, ["id", "texto"]), Risco.AMARELO, rascunho, lambda id, texto: f"guardar rascunho para {id}: {texto[:120]}"),
        Ferramenta("whatsapp_enviar", "Envia uma mensagem de WhatsApp em nome da pessoa.", esquema({"id": texto("id da conversa"), "texto": texto("mensagem")}, ["id", "texto"]), Risco.VERMELHO, enviar, lambda id, texto: f"ENVIAR no WhatsApp para {id}: \"{texto[:300]}\""),
        Ferramenta("atendimento_relatorio", "Números e achados do atendente automático de WhatsApp.", esquema({"dias": inteiro("1 a 30")}), Risco.VERDE, relatorio, lambda dias=1: f"relatório do atendente ({dias} dia(s))", externo=True),
    ]
