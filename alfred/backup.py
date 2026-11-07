"""Backup diário dos dados do Alfred (memória, checklist, registro de ações, configuração e rotinas).

- Um .zip por dia em  backups/alfred-AAAA-MM-DD.zip  (pasta do Alfred, fora do git), guarda os últimos 14.
- Bancos SQLite copiados pelo jeito seguro (API de backup do SQLite), mesmo com o Alfred usando.
- Nunca entra: chaves e senhas (estão no cofre do Windows, não em arquivo), cache da agenda, testes.
- Restaurar: feche o Alfred (parar-servico.ps1), descompacte o .zip por cima da pasta do Alfred e ligue de novo.
"""
import sqlite3
import tempfile
import threading
import time
import zipfile
from datetime import date
from pathlib import Path

from .config import BASE, DADOS

PASTA = BASE / "backups"
GUARDAR = 14
BANCOS = ["memoria.db", "tarefas.db"]
ARQUIVOS = ["auditoria.jsonl", "cota.json", "PROGRESSO.md", "instalados.md", "automacoes-log.jsonl"]


def fazer(hoje: date | None = None, dados: Path | None = None, pasta: Path | None = None, base: Path | None = None) -> Path:
    hoje, dados, pasta, base = hoje or date.today(), dados or DADOS, pasta or PASTA, base or BASE
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / f"alfred-{hoje.isoformat()}.zip"
    temp = destino.with_suffix(".tmp")
    for sobra in pasta.glob("*.tmp"):            # tentativa anterior que não terminou
        sobra.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp, zipfile.ZipFile(temp, "w", zipfile.ZIP_DEFLATED) as z:
        for nome in BANCOS:
            orig = dados / nome
            if orig.exists():
                copia = Path(tmp) / nome
                o, c = sqlite3.connect(orig), sqlite3.connect(copia)
                try:
                    o.backup(c)
                finally:                         # no Windows, arquivo aberto não pode ser apagado: fecha antes
                    c.close()
                    o.close()
                z.write(copia, f"dados/{nome}")
        for nome in ARQUIVOS:
            if (dados / nome).exists():
                z.write(dados / nome, f"dados/{nome}")
        for extra in [base / "config.toml", *sorted((base / "rotinas").glob("*.toml"))]:
            if extra.exists():
                z.write(extra, str(extra.relative_to(base)).replace("\\", "/"))
    temp.replace(destino)
    for velho in sorted(pasta.glob("alfred-*.zip"))[:-GUARDAR]:
        velho.unlink()
    return destino


def iniciar(parar: threading.Event, avisar=None) -> threading.Thread:
    """Confere de hora em hora: se ainda não há backup de hoje, faz (relógio de parede: funciona mesmo após o PC dormir)."""
    def laco():
        while not parar.is_set():
            try:
                if not (PASTA / f"alfred-{date.today().isoformat()}.zip").exists():
                    print(f"backup feito: {fazer().name}", flush=True)
            except Exception as e:
                print(f"backup falhou: {type(e).__name__}: {e}", flush=True)       # vai para dados/alfred.log
                if avisar:
                    avisar("erro", texto=f"backup falhou: {e}")
            parar.wait(3600)
    t = threading.Thread(target=laco, daemon=True, name="backup")
    t.start()
    return t
