"""Contador da cota do cérebro (Groq grátis e outros): mostra no painel e no Telegram (/cota) quanto já foi usado.

Duas fontes:
- O que o provedor informa a cada resposta (cabeçalhos x-ratelimit-*): pedidos restantes no dia e tokens livres no minuto.
- Uma contagem local de tokens do dia (o limite diário de tokens não vem nos cabeçalhos). É estimativa: a Groq pode
  contar o dia de outro jeito; o número oficial fica em console.groq.com/settings/limits.
"""
import json
import threading
import time

from .config import DADOS

ARQ = DADOS / "cota.json"
# Limites diários de tokens por modelo (plano grátis da Groq, conferidos na documentação em 03/nov/2026). Ajuste em config.toml: cota_tokens_dia.
TOKENS_DIA_PADRAO = {"groq": 200_000}
_trava = threading.Lock()


def _hoje() -> str:
    return time.strftime("%Y-%m-%d")


def _ler() -> dict:
    try:
        d = json.loads(ARQ.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    if d.get("dia") != _hoje():
        d = {"dia": _hoje(), "modelos": {}, "avisos": []}
    return d


def _int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def registrar(provedor: str, modelo: str, cabecalhos: dict | None, entrada: int, saida: int, limite_dia: int | None = None) -> str | None:
    """Soma o uso de uma resposta. Devolve um aviso quando o dia passa de 80% ou 95% da cota (uma vez cada)."""
    cab = {k.lower(): v for k, v in (cabecalhos or {}).items()}
    with _trava:
        d = _ler()
        m = d["modelos"].setdefault(f"{provedor}/{modelo}", {"tokens": 0, "pedidos": 0})
        m["tokens"] += int(entrada or 0) + int(saida or 0)
        m["pedidos"] += 1
        for chave, nome in (("x-ratelimit-limit-requests", "pedidos_limite_dia"), ("x-ratelimit-remaining-requests", "pedidos_restantes_dia"),
                            ("x-ratelimit-limit-tokens", "tokens_limite_minuto"), ("x-ratelimit-remaining-tokens", "tokens_livres_minuto")):
            if _int(cab.get(chave)) is not None:
                m[nome] = _int(cab[chave])
        m["atualizado"] = time.strftime("%H:%M:%S")
        limite = limite_dia or TOKENS_DIA_PADRAO.get(provedor)
        aviso = None
        if limite:
            m["tokens_limite_dia"] = limite
            pct = 100 * m["tokens"] / limite
            for marca in (95, 80):
                tag = f"{provedor}/{modelo}:{marca}"
                if pct >= marca and tag not in d["avisos"]:
                    d["avisos"] += [f"{provedor}/{modelo}:{x}" for x in (80, 95) if x <= marca]
                    aviso = f"Cota do dia em {pct:.0f}% ({m['tokens']:,} de {limite:,} tokens em {modelo}).".replace(",", ".")
                    break
        DADOS.mkdir(exist_ok=True)
        ARQ.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        return aviso


def somar_custo(chave: str, usd: float) -> None:
    """Custo estimado (equivalente em API) para quem informa, como o Claude Code."""
    with _trava:
        d = _ler()
        m = d["modelos"].setdefault(chave, {"tokens": 0, "pedidos": 0})
        m["usd_estimado"] = round(m.get("usd_estimado", 0.0) + float(usd or 0), 4)
        ARQ.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def estado() -> dict:
    with _trava:
        return _ler()


def resumo() -> str:
    """Texto curto para o Telegram e para a tela."""
    d = estado()
    if not d["modelos"]:
        return "Nenhum uso do cérebro hoje."
    linhas = [f"Uso do cérebro hoje ({d['dia']}):"]
    for nome, m in d["modelos"].items():
        partes = [f"{m['tokens']:,} tokens".replace(",", ".")]
        if m.get("tokens_limite_dia"):
            partes[0] += f" de {m['tokens_limite_dia']:,} ({100 * m['tokens'] / m['tokens_limite_dia']:.0f}%)".replace(",", ".")
        if m.get("pedidos_restantes_dia") is not None:
            partes.append(f"pedidos restantes hoje: {m['pedidos_restantes_dia']} de {m.get('pedidos_limite_dia', '?')}")
        else:
            partes.append(f"{m['pedidos']} pedidos")
        if m.get("usd_estimado") is not None:
            partes.append(f"equivale a US$ {m['usd_estimado']:.2f} na API (na assinatura não é cobrado)")
        if m.get("tokens_livres_minuto") is not None:
            partes.append(f"livres neste minuto: {m['tokens_livres_minuto']:,} de {m.get('tokens_limite_minuto', 0):,}".replace(",", "."))
        linhas.append(f"• {nome}: " + " · ".join(partes))
    linhas.append("(tokens do dia = contagem do Alfred, estimativa; oficial em console.groq.com/settings/limits)")
    return "\n".join(linhas)
