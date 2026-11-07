"""Cérebro: uma interface única (`pensar`) para qualquer provedor + o laço de ferramentas.

Formato interno das mensagens = estilo OpenAI (role/content/tool_calls). O adaptador da Anthropic converte.
Nomes de modelo mudam: confira a lista do dia do provedor (a API de modelos) antes de fixar um.
"""
import json
import re
import time
from dataclasses import dataclass, field

import httpx

from . import cota

from . import gate, segredos

PROVEDORES = {
    "groq":       {"tipo": "openai", "base": "https://api.groq.com/openai/v1", "modelo": "openai/gpt-oss-120b", "reserva": "openai/gpt-oss-20b", "chave": "groq"},
    "openai":     {"tipo": "openai", "base": "https://api.openai.com/v1", "modelo": "", "chave": "openai"},
    "openrouter": {"tipo": "openai", "base": "https://openrouter.ai/api/v1", "modelo": "", "chave": "openrouter"},
    "gemini":     {"tipo": "openai", "base": "https://generativelanguage.googleapis.com/v1beta/openai", "modelo": "", "chave": "gemini"},
    "xai":        {"tipo": "openai", "base": "https://api.x.ai/v1", "modelo": "", "chave": "xai"},
    "ollama":     {"tipo": "openai", "base": "http://localhost:11434/v1", "modelo": "", "chave": None},
    "anthropic":  {"tipo": "anthropic", "base": "https://api.anthropic.com/v1", "modelo": "claude-sonnet-5-5", "chave": "anthropic"},
}
# US$ por 1 milhão de tokens (entrada, saída): Anthropic em 06/out/2026. Outros: 0 = desconhecido/grátis.
PRECOS = {"claude-sonnet-5-5": (2.0, 10.0), "claude-haiku-5-5": (0.10, 0.50), "claude-opus-5-5": (4.0, 20.0), "claude-fable-5-1": (10.0, 50.0)}


class ErroCerebro(Exception):
    pass


@dataclass
class Resposta:
    texto: str = ""
    chamadas: list = field(default_factory=list)   # [{"id","nome","args"}]
    entrada: int = 0
    saida: int = 0


def _enxuto(esq: dict) -> dict:
    """Tira campos vazios do esquema (gasta menos tokens por chamada)."""
    e = {k: v for k, v in esq.items() if k != "additionalProperties" and not (k == "required" and not v)}
    return e


def _espera(r) -> float:
    """Segundos pedidos pelo provedor (Retry-After ou 'try again in 2.5s')."""
    try:
        if r.headers.get("retry-after"):
            return float(r.headers["retry-after"])
    except (ValueError, AttributeError):
        pass
    m = re.search(r"try again in ([\d.]+)(ms|s)", r.text or "")
    return (float(m.group(1)) / (1000 if m.group(2) == "ms" else 1) + 0.5) if m else 0.0


class Provedor:
    def __init__(self, nome: str, modelo: str = "", chave: str | None = None, base: str | None = None, reserva: str = ""):
        if nome not in PROVEDORES:
            raise ErroCerebro(f"provedor desconhecido: {nome}")
        p = PROVEDORES[nome]
        self.nome, self.tipo = nome, p["tipo"]
        self.base = (base or p["base"]).rstrip("/")
        self.modelo = modelo or p["modelo"]
        self.reserva = reserva or p.get("reserva", "")
        if not self.modelo:
            raise ErroCerebro(f"defina 'modelo' no config.toml para {nome} (veja a lista de modelos do provedor)")
        self.ultimos_cabecalhos: dict = {}
        self.chave = chave if chave is not None else (segredos.obter(p["chave"]) if p["chave"] else "")
        if p["chave"] and not self.chave:
            raise ErroCerebro(f"sem chave para {nome}. Rode: python -m alfred chave {p['chave']}")

    # -- HTTP com no máximo 3 tentativas e espera crescente (429/5xx) --
    def _post(self, url: str, cabecalhos: dict, corpo: dict) -> dict:
        ultimo = None
        for tentativa in range(3):
            try:
                r = httpx.post(url, headers=cabecalhos, json=corpo, timeout=60)
            except httpx.HTTPError as e:
                ultimo = f"rede: {e}"
            else:
                if r.status_code == 200:
                    self.ultimos_cabecalhos = dict(getattr(r, "headers", {}) or {})       # cota restante (x-ratelimit-*), lida pelo contador
                    return r.json()
                ultimo = f"{r.status_code}: {r.text[:300] or '(resposta vazia, servidor ' + r.headers.get('server', '?') + ')'}"
                if r.status_code not in (429, 500, 502, 503, 504, 529):
                    raise ErroCerebro(ultimo)
                if r.status_code == 429 and self.reserva and corpo.get("model") != self.reserva:
                    corpo = {**corpo, "model": self.reserva}      # cota do modelo principal estourou: tenta o menor
                    continue
                espera = _espera(r)
                if espera:
                    time.sleep(min(espera, 20))
                    continue
            time.sleep(1.5 * (tentativa + 1))
        if ultimo and ultimo.startswith("rede"):
            raise ErroCerebro(f"sem conexão com o cérebro ({self.nome}): confira a internet deste PC e tente de novo ({ultimo})")
        raise ErroCerebro(f"o provedor não respondeu ({ultimo})")

    def completar(self, sistema: str, mensagens: list, ferramentas: list) -> Resposta:
        if self.tipo == "anthropic":
            return self._anthropic(sistema, mensagens, ferramentas)
        return self._openai(sistema, mensagens, ferramentas)

    # ---------------- OpenAI-compatível (Groq, OpenAI, Gemini, xAI, OpenRouter, Ollama) ----------------
    def _openai(self, sistema, mensagens, ferramentas) -> Resposta:
        corpo = {"model": self.modelo, "messages": [{"role": "system", "content": sistema}] + mensagens, "max_tokens": 1200}
        if ferramentas:
            corpo["tools"] = [{"type": "function", "function": {"name": f["nome"], "description": f["descricao"], "parameters": _enxuto(f["parametros"])}} for f in ferramentas]
            corpo["tool_choice"] = "auto"
        cab = {"content-type": "application/json"}
        if self.chave:
            cab["authorization"] = f"Bearer {self.chave}"
        j = self._post(f"{self.base}/chat/completions", cab, corpo)
        msg = (j.get("choices") or [{}])[0].get("message") or {}
        chamadas = []
        for c in msg.get("tool_calls") or []:
            try:
                args = json.loads(c["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            chamadas.append({"id": c.get("id") or f"c{len(chamadas)}", "nome": c["function"]["name"], "args": args})
        uso = j.get("usage") or {}
        return Resposta((msg.get("content") or "").strip(), chamadas, uso.get("prompt_tokens", 0), uso.get("completion_tokens", 0))

    # ---------------- Anthropic (Messages API) ----------------
    def _anthropic(self, sistema, mensagens, ferramentas) -> Resposta:
        msgs = []
        for m in mensagens:
            if m["role"] == "assistant":
                blocos = ([{"type": "text", "text": m["content"]}] if m.get("content") else [])
                for c in m.get("tool_calls") or []:
                    blocos.append({"type": "tool_use", "id": c["id"], "name": c["function"]["name"], "input": json.loads(c["function"]["arguments"] or "{}")})
                msgs.append({"role": "assistant", "content": blocos or [{"type": "text", "text": "…"}]})
            elif m["role"] == "tool":
                bloco = {"type": "tool_result", "tool_use_id": m["tool_call_id"], "content": m["content"]}
                if msgs and msgs[-1]["role"] == "user" and isinstance(msgs[-1]["content"], list) and msgs[-1]["content"][0].get("type") == "tool_result":
                    msgs[-1]["content"].append(bloco)
                else:
                    msgs.append({"role": "user", "content": [bloco]})
            else:
                msgs.append({"role": "user", "content": m["content"]})
        corpo = {"model": self.modelo, "max_tokens": 1500, "system": sistema, "messages": msgs}   # sem temperature/budget_tokens (dão 400 nos modelos 5.x)
        if ferramentas:
            corpo["tools"] = [{"name": f["nome"], "description": f["descricao"], "input_schema": f["parametros"]} for f in ferramentas]
        j = self._post(f"{self.base}/messages", {"x-api-key": self.chave, "anthropic-version": "2023-06-01", "content-type": "application/json"}, corpo)
        texto, chamadas = "", []
        for b in j.get("content") or []:
            if b.get("type") == "text":
                texto += b.get("text", "")
            elif b.get("type") == "tool_use":
                chamadas.append({"id": b["id"], "nome": b["name"], "args": b.get("input") or {}})
        if j.get("stop_reason") == "refusal":
            texto = texto or "Não posso ajudar com isso."
        uso = j.get("usage") or {}
        return Resposta(texto.strip(), chamadas, uso.get("input_tokens", 0), uso.get("output_tokens", 0))

    def custo(self, r: Resposta) -> float:
        pe, ps = PRECOS.get(self.modelo, (0.0, 0.0))
        return (r.entrada * pe + r.saida * ps) / 1e6


# ------------------------------------------------------------------ laço de ferramentas
MAX_PASSOS = 8


def pensar(provedor: Provedor, sistema: str, historico: list, registro, emitir, confirmar, modo: str,
           sempre: set | None = None, ativos: set | None = None) -> str:
    """Roda o laço: modelo -> ferramentas (pelo portão) -> modelo... até responder. Retorna o texto final.

    registro: objeto com .esquemas() e .executar(nome, args, confirmar, modo, sempre) -> dict
    emitir(tipo, **dados): notifica a tela. historico é alterado (acrescenta as mensagens do turno).
    """
    for _ in range(MAX_PASSOS):
        ferramentas = registro.esquemas(modo, ativos)     # recalcula: habilitar_grupo muda o que o modelo enxerga
        if gate.PARADO.is_set():
            return "Parei, como você pediu."
        r = provedor.completar(sistema, historico, ferramentas)
        gate.somar_gasto(provedor.custo(r))
        emitir("uso", entrada=r.entrada, saida=r.saida, usd=round(provedor.custo(r), 5))
        try:
            aviso = cota.registrar(getattr(provedor, "nome", "?"), getattr(provedor, "modelo", "?"), getattr(provedor, "ultimos_cabecalhos", {}),
                                   r.entrada, r.saida, getattr(provedor, "limite_tokens_dia", None))
            if aviso:
                emitir("erro", texto=aviso)
        except Exception:
            pass        # o contador nunca pode derrubar uma conversa
        if not r.chamadas:
            historico.append({"role": "assistant", "content": r.texto})
            return r.texto or "(sem resposta)"
        historico.append({"role": "assistant", "content": r.texto or None, "tool_calls": [
            {"id": c["id"], "type": "function", "function": {"name": c["nome"], "arguments": json.dumps(c["args"], ensure_ascii=False)}} for c in r.chamadas]})
        for c in r.chamadas:
            if gate.PARADO.is_set():
                return "Parei, como você pediu."
            emitir("ferramenta", nome=c["nome"], args=c["args"])
            res = registro.executar(c["nome"], c["args"], confirmar, modo, sempre or set(), ativos)
            emitir("resultado", nome=c["nome"], ok=bool(res.get("ok")), resumo=str(res.get("saida") or res.get("motivo"))[:300])
            historico.append({"role": "tool", "tool_call_id": c["id"], "content": json.dumps(res, ensure_ascii=False)[:3500]})
    return "Fiz o que pude em 8 passos e parei para não entrar em loop. Quer que eu continue?"
