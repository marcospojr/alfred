"""Cliente MCP (stdio): conecta o Alfred a QUALQUER servidor MCP (GitHub, Notion, Google, bancos de dados, navegadores...).
As ferramentas do servidor viram ferramentas do Alfred (prefixo mcp_<servidor>_), todas pelo portão de risco.
Servidores remotos com OAuth: use uma ponte local, por exemplo  npx mcp-remote https://servidor/mcp  como comando."""
import json
import os
import re
import shutil
import subprocess
import threading
from pathlib import Path

from . import segredos
from .config import BASE
from .gate import Risco

ARQUIVO = BASE / "mcp.json"
NOME_OK = re.compile(r"^[a-z0-9][a-z0-9-]{1,19}$")
VERSAO = "2025-06-18"


class ErroMcp(RuntimeError):
    pass


class ClienteMcp:
    def __init__(self, comando: str, args: list[str], env: dict | None = None, cwd: str | None = None):
        exe = shutil.which(comando)
        if not exe:
            raise ErroMcp(f"programa '{comando}' não encontrado no PATH (instale o Node.js ou o programa do servidor)")
        base = {k: os.environ[k] for k in ("PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "TEMP", "TMP", "LANG", "APPDATA", "LOCALAPPDATA") if k in os.environ}
        self.proc = subprocess.Popen([exe, *args], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
                                     bufsize=1, env={**base, **(env or {})}, cwd=cwd)
        self._n, self._pend, self._trava = 0, {}, threading.Lock()
        threading.Thread(target=self._ler, daemon=True).start()

    def _ler(self):
        for linha in self.proc.stdout:
            try:
                m = json.loads(linha)
            except json.JSONDecodeError:
                continue
            if "id" in m and ("result" in m or "error" in m):
                ev = self._pend.get(m["id"])
                if ev:
                    ev["resp"] = m
                    ev["ev"].set()
            elif "id" in m and "method" in m:          # pedido do servidor ao cliente (roots, sampling...): não oferecemos
                self._enviar({"jsonrpc": "2.0", "id": m["id"], "error": {"code": -32601, "message": "não suportado pelo Alfred"}})

    def _enviar(self, msg: dict):
        with self._trava:
            self.proc.stdin.write(json.dumps(msg) + "\n")
            self.proc.stdin.flush()

    def chamar(self, metodo: str, params: dict | None = None, timeout: float = 30):
        with self._trava:
            self._n += 1
            i = self._n
        ev = {"ev": threading.Event(), "resp": None}
        self._pend[i] = ev
        self._enviar({"jsonrpc": "2.0", "id": i, "method": metodo, "params": params or {}})
        if not ev["ev"].wait(timeout):
            self._pend.pop(i, None)
            raise ErroMcp(f"o servidor MCP não respondeu a '{metodo}' em {timeout:.0f}s")
        self._pend.pop(i, None)
        r = ev["resp"]
        if "error" in r:
            raise ErroMcp(f"{r['error'].get('message')}")
        return r["result"]

    def iniciar(self):
        self.chamar("initialize", {"protocolVersion": VERSAO, "capabilities": {}, "clientInfo": {"name": "alfred-kit", "version": "1.0.0"}}, timeout=45)
        self._enviar({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def ferramentas(self) -> list[dict]:
        saida, cursor = [], None
        for _ in range(20):
            r = self.chamar("tools/list", {"cursor": cursor} if cursor else {})
            saida += r.get("tools", [])
            cursor = r.get("nextCursor")
            if not cursor:
                break
        return saida

    def executar(self, nome: str, args: dict) -> str:
        r = self.chamar("tools/call", {"name": nome, "arguments": args}, timeout=120)
        partes = [c.get("text", "") if c.get("type") == "text" else f"[{c.get('type')}]" for c in r.get("content", [])]
        texto = "\n".join(partes) or json.dumps(r.get("structuredContent", ""), ensure_ascii=False)
        if r.get("isError"):
            raise ErroMcp(texto[:500])
        return texto

    def fechar(self):
        try:
            self.proc.terminate()
        except Exception:
            pass


def _esquema(s: dict | None) -> dict:
    s = s if isinstance(s, dict) and s.get("type") == "object" else {"type": "object", "properties": {}}
    return {"type": "object", "properties": s.get("properties", {}), "required": s.get("required", [])}


def _executor(cli, original):
    return lambda **a: cli.executar(original, a)


def _frase(nome):
    return lambda **a: f"usar {nome} com {json.dumps(a, ensure_ascii=False)[:300]}"


class GerenteMcp:
    """Mantém os servidores conectados e registra as ferramentas deles no registro do Alfred."""

    def __init__(self, ctx, arquivo: Path | None = None):
        self.ctx = ctx
        self.arquivo = arquivo or ARQUIVO
        self.clientes: dict[str, ClienteMcp] = {}
        self.erros: dict[str, str] = {}

    def config(self) -> list[dict]:
        return json.loads(self.arquivo.read_text(encoding="utf-8")) if self.arquivo.exists() else []

    def salvar_config(self, lista: list[dict]):
        self.arquivo.write_text(json.dumps(lista, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def validar(d: dict) -> dict:
        if not isinstance(d, dict) or set(d) - {"nome", "comando", "args", "env", "risco", "leitura"}:
            raise ErroMcp("chaves permitidas: nome, comando, args, env, risco, leitura")
        if not NOME_OK.match(str(d.get("nome", ""))):
            raise ErroMcp("'nome': 2 a 20 caracteres, minúsculas, números e hífen")
        if not d.get("comando") or re.search(r"[;&|<>`$\n]", d["comando"]):
            raise ErroMcp("'comando' deve ser só o nome do programa (ex.: npx), os argumentos vão em 'args'")
        return {"nome": d["nome"], "comando": d["comando"], "args": [str(a) for a in d.get("args", [])], "env": dict(d.get("env", {})),
                "risco": d.get("risco", "A") if d.get("risco", "A") in ("A", "R") else "A", "leitura": list(d.get("leitura", []))}

    def conectar(self, c: dict) -> list:
        from .tools import Ferramenta
        env = {k: (segredos.obter(v[1:]) or "") if str(v).startswith("@") else str(v) for k, v in c.get("env", {}).items()}
        cli = ClienteMcp(c["comando"], c.get("args", []), env)
        try:
            cli.iniciar()
            tools = cli.ferramentas()
        except Exception:
            cli.fechar()
            raise
        self.clientes[c["nome"]] = cli
        novas = []
        for t in tools:
            nome = f"mcp_{c['nome']}_{re.sub(r'[^a-zA-Z0-9_]', '_', t['name'])}"[:60]
            leitura = t["name"] in c.get("leitura", [])
            risco = Risco.VERDE if leitura else (Risco.VERMELHO if c.get("risco") == "R" else Risco.AMARELO)
            novas.append(Ferramenta(nome, f"[MCP {c['nome']}] {t.get('description', '')[:300]}", _esquema(t.get("inputSchema")), risco,
                                    _executor(cli, t["name"]), _frase(nome), externo=True))
        return novas

    def iniciar(self, bloquear: bool = False):
        """Conecta todos os servidores configurados em segundo plano (não trava a abertura do Alfred)."""
        def tarefa(c):
            try:
                for f in self.conectar(c):
                    self.ctx.agente.registro.adicionar(f)
                self.erros.pop(c["nome"], None)
            except Exception as e:
                self.erros[c["nome"]] = str(e)
        ths = [threading.Thread(target=tarefa, args=(c,), daemon=True) for c in self.config()]
        for t in ths:
            t.start()
        if bloquear:
            for t in ths:
                t.join(60)

    def parar(self):
        for c in self.clientes.values():
            c.fechar()
