"""Mini-apps: telas que o Alfred cria para você (HTML/JS/CSS) e serve em http://127.0.0.1:PORTA/apps/<nome>/.
Cada app tem um token PRÓPRIO que só abre o armazenamento dele e a pergunta ao Alfred (somente leitura).
Ele nunca recebe o token principal: um app gerado por IA não pode aprovar confirmações nem usar ferramentas de ação."""
import hashlib
import hmac
import json
import re
import shutil
import time
from pathlib import Path

from .config import BASE

PASTA = BASE / "apps"
NOME_OK = re.compile(r"^[a-z0-9][a-z0-9_-]{1,39}$")
ARQ_OK = re.compile(r"^[\w.-]{1,50}$")
EXT_OK = {".html", ".js", ".css", ".json", ".txt", ".svg", ".md"}
MAX_ARQ = 400_000
CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
       "connect-src 'self'; font-src 'self' data:; frame-ancestors 'self'; base-uri 'none'; form-action 'self'; object-src 'none'")

AJUDANTE = """<script>window.ALFRED_APP={nome:"__NOME__",token:"__TOKEN__",
async lerDados(){const r=await fetch("/api/app/__NOME__/dados",{headers:{"x-app-token":this.token}});return (await r.json()).dados},
async salvarDados(d){const r=await fetch("/api/app/__NOME__/dados",{method:"PUT",headers:{"x-app-token":this.token,"content-type":"application/json"},body:JSON.stringify(d)});if(!r.ok)throw new Error((await r.json()).detail||r.status);return true},
async perguntar(t){const r=await fetch("/api/app/__NOME__/perguntar",{method:"POST",headers:{"x-app-token":this.token,"content-type":"application/json"},body:JSON.stringify({texto:t})});const j=await r.json();if(!r.ok)throw new Error(j.detail||r.status);return j.texto}};</script>"""


class ErroApp(ValueError):
    pass


def validar_novo(nome: str, titulo: str, html: str, arquivos: dict | None = None) -> None:
    if not NOME_OK.match(nome or ""):
        raise ErroApp("nome do app: 2 a 40 caracteres, letras minúsculas, números, hífen ou _")
    if not html or "<" not in html:
        raise ErroApp("'html' deve ser um index.html completo")
    for n, c in {"index.html": html, **(arquivos or {})}.items():
        if not ARQ_OK.match(n) or Path(n).suffix.lower() not in EXT_OK:
            raise ErroApp(f"arquivo '{n}' não permitido (extensões: {sorted(EXT_OK)})")
        if len(str(c)) > MAX_ARQ:
            raise ErroApp(f"'{n}' passa de {MAX_ARQ} caracteres")


class GerenteApps:
    def __init__(self, segredo: str, pasta: Path | None = None):
        self.segredo = segredo.encode()
        self.pasta = pasta or PASTA
        self.pasta.mkdir(exist_ok=True)

    def token(self, nome: str) -> str:
        return hmac.new(self.segredo, f"app:{nome}".encode(), hashlib.sha256).hexdigest()[:40]

    def token_ok(self, nome: str, token: str | None) -> bool:
        return bool(token) and hmac.compare_digest(token, self.token(nome))

    def _dir(self, nome: str) -> Path:
        if not NOME_OK.match(nome or ""):
            raise ErroApp("nome do app: 2 a 40 caracteres, letras minúsculas, números, hífen ou _")
        return self.pasta / nome

    def criar(self, nome: str, titulo: str, html: str, descricao: str = "", arquivos: dict | None = None, sobrescrever: bool = False) -> Path:
        d = self._dir(nome)
        if d.exists() and not sobrescrever:
            raise ErroApp(f"o app '{nome}' já existe (use app_atualizar)")
        d.mkdir(parents=True, exist_ok=True)
        todos = {"index.html": html, **(arquivos or {})}
        for n, c in todos.items():
            if not ARQ_OK.match(n) or Path(n).suffix.lower() not in EXT_OK:
                raise ErroApp(f"arquivo '{n}' não permitido (extensões: {sorted(EXT_OK)})")
            if len(c) > MAX_ARQ:
                raise ErroApp(f"'{n}' passa de {MAX_ARQ} caracteres")
            (d / n).write_text(c, encoding="utf-8")
        (d / "app.json").write_text(json.dumps({"nome": nome, "titulo": titulo[:80], "descricao": descricao[:300], "criado_em": time.strftime("%Y-%m-%d %H:%M")}, ensure_ascii=False), encoding="utf-8")
        return d

    def listar(self) -> list[dict]:
        out = []
        for d in sorted(self.pasta.iterdir()):
            f = d / "app.json"
            if d.is_dir() and f.exists():
                out.append(json.loads(f.read_text(encoding="utf-8")))
        return out

    def ler(self, nome: str, arquivo: str = "index.html") -> str:
        f = self._dir(nome) / arquivo
        if not ARQ_OK.match(arquivo) or not f.exists():
            raise ErroApp("arquivo não encontrado")
        return f.read_text(encoding="utf-8")

    def atualizar(self, nome: str, html: str, arquivos: dict | None = None) -> None:
        d = self._dir(nome)
        if not d.exists():
            raise ErroApp(f"o app '{nome}' não existe")
        meta = json.loads((d / "app.json").read_text(encoding="utf-8"))
        self.criar(nome, meta.get("titulo", nome), html, meta.get("descricao", ""), arquivos, sobrescrever=True)

    def excluir(self, nome: str) -> None:
        d = self._dir(nome)
        if not d.exists():
            raise ErroApp("não existe")
        lixo = self.pasta / "_lixeira"
        lixo.mkdir(exist_ok=True)
        shutil.move(str(d), str(lixo / f"{nome}-{int(time.time())}"))

    # ---- servir ----
    def servir(self, nome: str, arquivo: str) -> tuple[bytes, str]:
        d = self._dir(nome)
        arquivo = arquivo or "index.html"
        f = d / arquivo
        if not ARQ_OK.match(arquivo) or not f.is_file() or arquivo == "app.json":
            raise ErroApp("não encontrado")
        tipo = {".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".svg": "image/svg+xml"}.get(f.suffix.lower(), "text/plain")
        corpo = f.read_text(encoding="utf-8")
        if f.suffix.lower() == ".html":
            aj = AJUDANTE.replace("__NOME__", nome).replace("__TOKEN__", self.token(nome))
            corpo = corpo.replace("<head>", "<head>" + aj, 1) if "<head>" in corpo else aj + corpo
        return corpo.encode("utf-8"), tipo + "; charset=utf-8"

    # ---- dados do app (um JSON por app) ----
    def dados(self, nome: str) -> object:
        f = self._dir(nome) / "dados.json"
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}

    def salvar_dados(self, nome: str, valor: object) -> None:
        txt = json.dumps(valor, ensure_ascii=False)
        if len(txt) > 1_000_000:
            raise ErroApp("dados passam de 1 MB")
        (self._dir(nome) / "dados.json").write_text(txt, encoding="utf-8")
