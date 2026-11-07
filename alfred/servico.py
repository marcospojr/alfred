"""Alfred como serviço: roda escondido (sem janela), reabre se cair e reinicia quando você pede pelo Telegram (/reiniciar).

python -m alfred servico   -> o "vigia": abre o Alfred como processo filho e o reabre quando ele sai.
- Uma cópia só: o vigia segura uma porta local (porta + 1); um segundo vigia sai na hora.
- Saída 75 = reinício pedido (volta na hora). Saída 0 = encerrou de propósito (ex.: já havia outro Alfred aberto): o vigia para.
  Qualquer outra saída = caiu: volta com espera crescente (5 s, 10 s, 20 s... até 60 s).
- Log em dados/alfred.log (gira em 5 MB, guarda 1 anterior), porque sem janela não há onde ler os avisos.
"""
import os
import socket
import subprocess
import sys
import time

from .config import BASE, DADOS, carregar

REINICIAR = 75
LOG = DADOS / "alfred.log"
LOG_MAX = 5_000_000


def porta_ocupada(porta: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, porta)) == 0


def trava_unica(porta: int):
    """Segura uma porta local enquanto o vigia vive. Devolve o socket, ou None se já existe outro vigia."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):          # Windows: ninguém mais consegue usar a mesma porta
        s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    try:
        s.bind(("127.0.0.1", porta))
        s.listen(1)
        return s
    except OSError:
        s.close()
        return None


def girar_log(arq=None, limite: int = LOG_MAX) -> None:
    arq = arq or LOG
    if arq.exists() and arq.stat().st_size > limite:
        velho = arq.with_suffix(".log.1")
        if velho.exists():
            velho.unlink()
        arq.rename(velho)


def _iniciar_filho():
    DADOS.mkdir(exist_ok=True)
    girar_log()
    log = open(LOG, "a", encoding="utf-8", errors="replace")
    log.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} Alfred iniciando =====\n")
    log.flush()
    env = {**os.environ, "ALFRED_SERVICO": "1", "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
    flags = subprocess.CREATE_NO_WINDOW if sys.platform.startswith("win") else 0
    p = subprocess.Popen([sys.executable, "-m", "alfred", "--sem-navegador"], cwd=str(BASE), stdout=log, stderr=subprocess.STDOUT,
                         env=env, creationflags=flags)
    p._log = log
    return p


def vigiar(iniciar=_iniciar_filho, dormir=time.sleep, max_ciclos: int | None = None) -> int:
    """Laço do vigia. iniciar() -> processo com .wait(); testável com falsos."""
    espera, ciclos = 5, 0
    while max_ciclos is None or ciclos < max_ciclos:
        ciclos += 1
        inicio = time.time()
        p = iniciar()
        codigo = p.wait()
        if getattr(p, "_log", None):
            p._log.write(f"===== {time.strftime('%Y-%m-%d %H:%M:%S')} Alfred saiu com código {codigo} =====\n")
            p._log.close()
        if codigo == 0:
            return 0
        if codigo == REINICIAR:
            espera = 5
            continue
        if time.time() - inicio > 600:     # ficou de pé bastante tempo: a queda não é em série
            espera = 5
        dormir(espera)
        espera = min(espera * 2, 60)
    return 1


def rodar() -> int:
    cfg = carregar()
    trava = trava_unica(int(cfg["porta"]) + 1)
    if trava is None:
        print("o vigia do Alfred já está rodando")
        return 0
    try:
        return vigiar()
    finally:
        trava.close()
