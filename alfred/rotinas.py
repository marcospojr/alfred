"""Rotinas: pedidos que rodam sozinhos em horários fixos, em modo 'observar' (só leitura).
Usam o RELÓGIO DE PAREDE: se o computador dormiu na hora, a rotina roda quando ele acordar (no mesmo dia)."""
import threading
import time
import tomllib
from datetime import datetime
from pathlib import Path

from .config import BASE, DADOS

PASTAS = [BASE / "presets" / "rotinas", BASE / "rotinas"]
DIAS = ["seg", "ter", "qua", "qui", "sex", "sab", "dom"]


def carregar() -> list[dict]:
    rot = []
    for pasta in PASTAS:
        for f in sorted(pasta.glob("*.toml")):
            with f.open("rb") as fh:
                r = tomllib.load(fh)
            if r.get("ativa", False):
                rot.append({"nome": f.stem, **r})
    return rot


def rodar_pendentes(rotinas: list[dict], executar, agora: datetime | None = None, estado_arq: Path | None = None) -> list[str]:
    """executar(pedido) -> texto. Retorna os nomes das rotinas disparadas. Chamável em teste com `agora`."""
    agora = agora or datetime.now()
    arq = estado_arq or (DADOS / "rotinas-estado.txt")
    feitas = set(arq.read_text(encoding="utf-8").split("\n")) if arq.exists() else set()
    disparadas = []
    for r in rotinas:
        dias = r.get("dias") or DIAS
        if DIAS[agora.weekday()] not in dias:
            continue
        h, m = (int(x) for x in r.get("hora", "08:00").split(":"))
        marca = f"{agora:%Y-%m-%d}|{r['nome']}"
        if (agora.hour, agora.minute) >= (h, m) and marca not in feitas:
            feitas.add(marca)
            arq.write_text("\n".join(sorted(feitas)[-200:]), encoding="utf-8")
            executar(r)
            disparadas.append(r["nome"])
    return disparadas


def iniciar(executar, parar: threading.Event) -> threading.Thread:
    rotinas = carregar()

    def laco():
        while not parar.is_set():
            try:
                rodar_pendentes(rotinas, executar)
            except Exception as e:  # uma rotina ruim não derruba as outras
                print("rotina falhou:", e)
            parar.wait(30)

    t = threading.Thread(target=laco, daemon=True, name="rotinas")
    t.start()
    return t
