"""Memória permanente em SQLite (fatos + conversa + busca de texto). Receita da seção 7 do manual."""
import re
import sqlite3
import threading
from pathlib import Path

from .config import DADOS

ESQUEMA = """
CREATE TABLE IF NOT EXISTS fatos (
  id INTEGER PRIMARY KEY, chave TEXT NOT NULL UNIQUE, valor TEXT NOT NULL, origem TEXT,
  criado_em TEXT DEFAULT (datetime('now','localtime')), atualizado_em TEXT DEFAULT (datetime('now','localtime')));
CREATE TABLE IF NOT EXISTS conversa (
  id INTEGER PRIMARY KEY, quando TEXT DEFAULT (datetime('now','localtime')),
  quem TEXT CHECK (quem IN ('voce','assistente')), texto TEXT NOT NULL);
CREATE VIRTUAL TABLE IF NOT EXISTS conversa_fts USING fts5(
  texto, content='conversa', content_rowid='id', tokenize='unicode61 remove_diacritics 2');
CREATE TRIGGER IF NOT EXISTS conversa_ai AFTER INSERT ON conversa BEGIN
  INSERT INTO conversa_fts(rowid, texto) VALUES (new.id, new.texto); END;
CREATE TRIGGER IF NOT EXISTS conversa_ad AFTER DELETE ON conversa BEGIN
  INSERT INTO conversa_fts(conversa_fts, rowid, texto) VALUES ('delete', old.id, old.texto); END;
"""


class Memoria:
    def __init__(self, caminho: Path | None = None):
        self.caminho = caminho or (DADOS / "memoria.db")
        self._lock = threading.Lock()
        self.con = sqlite3.connect(self.caminho, check_same_thread=False)
        self.con.executescript(ESQUEMA)

    def lembrar(self, chave: str, valor: str, origem: str = "conversa") -> None:
        with self._lock, self.con:
            self.con.execute(
                "INSERT INTO fatos(chave,valor,origem) VALUES(?,?,?) ON CONFLICT(chave) DO UPDATE SET "
                "valor=excluded.valor, atualizado_em=datetime('now','localtime')", (chave.strip(), valor.strip(), origem))

    def esquecer(self, chave: str) -> int:
        with self._lock, self.con:
            return self.con.execute("DELETE FROM fatos WHERE chave = ?", (chave.strip(),)).rowcount

    def fatos(self) -> list[tuple[str, str]]:
        with self._lock:
            return self.con.execute("SELECT chave, valor FROM fatos ORDER BY atualizado_em DESC").fetchall()

    def registrar(self, quem: str, texto: str) -> None:
        with self._lock, self.con:
            self.con.execute("INSERT INTO conversa(quem,texto) VALUES(?,?)", (quem, texto))

    @staticmethod
    def _consulta(q: str) -> str:
        termos = re.findall(r"\w{2,}", q, flags=re.UNICODE)
        return " OR ".join(f'"{t}"' for t in termos[:8])

    def buscar(self, q: str, n: int = 5) -> list[tuple[str, str, str]]:
        """(quando, quem, trecho) das conversas; sem acento também acha ('reuniao' acha 'reunião')."""
        consulta = self._consulta(q)
        if not consulta:
            return []
        with self._lock:
            return self.con.execute(
                "SELECT c.quando, c.quem, snippet(conversa_fts,0,'[',']','…',10) FROM conversa_fts "
                "JOIN conversa c ON c.id = conversa_fts.rowid WHERE conversa_fts MATCH ? ORDER BY rank LIMIT ?",
                (consulta, n)).fetchall()

    def lembrancas_para(self, pergunta: str) -> str:
        """Texto curto com fatos + trechos relevantes (nunca a memória inteira)."""
        partes = [f"- {k}: {v}" for k, v in self.fatos()[:15]]
        for quando, quem, trecho in self.buscar(pergunta, 5):
            partes.append(f"- em {quando[:10]} ({quem}): {trecho}")
        return "\n".join(partes) if partes else "(nenhuma lembrança ainda)"

    def apagar_tudo(self) -> None:
        with self._lock, self.con:
            self.con.executescript("DELETE FROM fatos; DELETE FROM conversa; INSERT INTO conversa_fts(conversa_fts) VALUES('rebuild');")
