"""Backup: copia bancos com segurança (mesmo abertos), arquivos, config e rotinas; guarda só 14; nunca leva cache."""
import sqlite3
import zipfile
from datetime import date, timedelta

from alfred import backup


def test_backup_completo_e_giro(tmp_path):
    dados, base, pasta = tmp_path / "dados", tmp_path, tmp_path / "backups"
    dados.mkdir()
    (base / "rotinas").mkdir()
    con = sqlite3.connect(dados / "memoria.db")              # aberto, como no Alfred rodando
    con.execute("CREATE TABLE fatos (chave TEXT, valor TEXT)")
    con.execute("INSERT INTO fatos VALUES ('loja', 'Be Aesthetic')")
    con.commit()
    (dados / "auditoria.jsonl").write_text("{}\n")
    (dados / "agenda-cache.ics").write_text("BEGIN:VCALENDAR")
    (base / "config.toml").write_text("nome = 'Alfred'")
    (base / "rotinas" / "bom-dia.toml").write_text("ativa = true")
    z = backup.fazer(date(2026, 11, 4), dados, pasta, base)
    nomes = zipfile.ZipFile(z).namelist()
    assert {"dados/memoria.db", "dados/auditoria.jsonl", "config.toml", "rotinas/bom-dia.toml"} <= set(nomes)
    assert "dados/agenda-cache.ics" not in nomes
    zipfile.ZipFile(z).extract("dados/memoria.db", tmp_path / "rest")
    assert sqlite3.connect(tmp_path / "rest" / "dados" / "memoria.db").execute("SELECT valor FROM fatos").fetchone() == ("Be Aesthetic",)
    for i in range(20):
        backup.fazer(date(2026, 11, 4) + timedelta(days=i + 1), dados, pasta, base)
    assert len(list(pasta.glob("alfred-*.zip"))) == 14
    con.close()


def test_limpa_tentativa_anterior_e_fecha_arquivos(tmp_path):
    dados, pasta = tmp_path / "dados", tmp_path / "backups"
    dados.mkdir()
    pasta.mkdir()
    (pasta / "alfred-2026-11-04.tmp").write_text("sobra")
    sqlite3.connect(dados / "tarefas.db").close()
    z = backup.fazer(date(2026, 11, 5), dados, pasta, tmp_path)
    assert z.exists() and not list(pasta.glob("*.tmp"))
    (dados / "tarefas.db").unlink()                    # no Windows isso falharia se a cópia tivesse deixado o banco aberto
