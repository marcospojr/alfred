import json, time, threading
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable

class Risco(str, Enum):
    VERDE = "V"      # só lê, não muda nada
    AMARELO = "A"    # muda algo que dá para desfazer
    VERMELHO = "R"   # apaga, envia para fora, gasta dinheiro, não tem volta

@dataclass
class Ferramenta:
    nome: str
    risco: Risco
    executar: Callable[..., Any]
    frase: Callable[..., str]          # descreve a ação em português claro, com os valores reais

PARADO = threading.Event()             # botão de parada: qualquer ponto do código checa
LOG = Path(__file__).resolve().parent.parent / "dados" / "auditoria.jsonl"   # fixo: não depende da pasta de onde abriram o Alfred
LIMITE_DIARIO_USD = 2.00               # teto de gasto de API por dia (ajuste)
_gasto_hoje = {"dia": "", "usd": 0.0}

def registrar(evento: dict) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    evento["quando"] = time.strftime("%Y-%m-%d %H:%M:%S")
    with LOG.open("a", encoding="utf-8") as f:   # só acrescenta; nunca reescreve
        f.write(json.dumps(evento, ensure_ascii=False) + "\n")

def somar_gasto(usd: float) -> None:
    hoje = time.strftime("%Y-%m-%d")
    if _gasto_hoje["dia"] != hoje:
        _gasto_hoje.update(dia=hoje, usd=0.0)
    _gasto_hoje["usd"] += usd

def rodar(f: Ferramenta, args: dict, confirmar: Callable[[str], bool], auto_amarelo: bool = False, pre_aprovado: bool = False) -> dict:
    """confirmar() pergunta à PESSOA (voz 'sim' ou clique). Nunca ao modelo."""
    if PARADO.is_set():
        return {"ok": False, "motivo": "parado pela pessoa"}
    if _gasto_hoje["usd"] >= LIMITE_DIARIO_USD:
        return {"ok": False, "motivo": "limite diário de gasto atingido"}
    texto = f.frase(**args)
    precisa = (f.risco is Risco.VERMELHO and not pre_aprovado) or (f.risco is Risco.AMARELO and not auto_amarelo)
    if pre_aprovado:
        texto = "[liberada por você no config.toml] " + texto
    if precisa and not confirmar(texto):
        registrar({"ferramenta": f.nome, "risco": f.risco.value, "acao": texto, "resultado": "recusado"})
        return {"ok": False, "motivo": "a pessoa não confirmou"}
    try:
        saida = f.executar(**args)
        resultado = {"ok": True, "saida": saida}
    except Exception as e:                      # erro vira dado, não vira "concluído"
        resultado = {"ok": False, "motivo": f"{type(e).__name__}: {e}"}
    registrar({"ferramenta": f.nome, "risco": f.risco.value, "acao": texto,
               "resultado": "ok" if resultado["ok"] else resultado["motivo"]})
    return resultado
