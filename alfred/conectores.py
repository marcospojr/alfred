"""Conectores: o Alfred conversa com QUALQUER API HTTP descrita num arquivo JSON em conectores/.
A chave fica no cofre do sistema (python -m alfred chave <segredo>); o modelo nunca vê a chave.
Leitura (risco V) e ação (A/R) são ferramentas diferentes: só a de ação passa pelo portão com confirmação."""
import json
import re
import urllib.parse
from pathlib import Path

import httpx

from . import segredos
from .config import BASE
from .tools.web import url_publica

PASTA = BASE / "conectores"
NOME_OK = re.compile(r"^[a-z0-9][a-z0-9_-]{1,39}$")
METODOS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
AUTH = {"nenhum", "bearer", "header", "query"}


class ErroConector(ValueError):
    pass


def validar(d: dict) -> dict:
    if not isinstance(d, dict):
        raise ErroConector("a definição deve ser um objeto JSON")
    ok = {"nome", "descricao", "base_url", "auth", "endpoints", "local"}
    if set(d) - ok:
        raise ErroConector(f"chaves desconhecidas: {sorted(set(d) - ok)}. Permitidas: {sorted(ok)}")
    if not NOME_OK.match(str(d.get("nome", ""))):
        raise ErroConector("'nome': 2 a 40 caracteres, minúsculas, números, hífen ou _")
    base = str(d.get("base_url", ""))
    u = urllib.parse.urlparse(base)
    if u.scheme != "https" and not (d.get("local") and u.hostname in ("localhost", "127.0.0.1")):
        raise ErroConector("'base_url' precisa ser https (http só para localhost com \"local\": true)")
    auth = d.get("auth") or {"tipo": "nenhum"}
    if auth.get("tipo") not in AUTH:
        raise ErroConector(f"auth.tipo deve ser um de {sorted(AUTH)}")
    if auth["tipo"] != "nenhum" and not re.match(r"^[\w-]{2,40}$", str(auth.get("segredo", ""))):
        raise ErroConector("auth.segredo: nome da entrada no cofre (a pessoa guarda com: python -m alfred chave <nome>)")
    if auth["tipo"] in ("header", "query") and not auth.get("campo"):
        raise ErroConector("auth.campo: nome do cabeçalho ou do parâmetro (ex.: X-API-Key)")
    eps = d.get("endpoints")
    if not isinstance(eps, list) or not eps:
        raise ErroConector("'endpoints' deve ser uma lista com pelo menos 1 item")
    vistos = set()
    for e in eps:
        if set(e) - {"nome", "metodo", "caminho", "descricao", "risco", "parametros"}:
            raise ErroConector("endpoint aceita: nome, metodo, caminho, descricao, risco, parametros")
        if not NOME_OK.match(str(e.get("nome", ""))) or e["nome"] in vistos:
            raise ErroConector("cada endpoint precisa de 'nome' único (minúsculas, números, hífen ou _)")
        vistos.add(e["nome"])
        if e.get("metodo", "GET").upper() not in METODOS:
            raise ErroConector(f"metodo deve ser um de {sorted(METODOS)}")
        if not str(e.get("caminho", "")).startswith("/"):
            raise ErroConector("'caminho' deve começar com / (ex.: /ws/{cep}/json/)")
        if e.get("risco", "V" if e.get("metodo", "GET").upper() == "GET" else "A") not in ("V", "A", "R"):
            raise ErroConector("'risco' deve ser V (só lê), A (muda algo reversível) ou R (apaga/envia/gasta)")
    return {"nome": d["nome"], "descricao": str(d.get("descricao", ""))[:300], "base_url": base.rstrip("/"), "auth": auth, "local": bool(d.get("local")),
            "endpoints": [{"nome": e["nome"], "metodo": e.get("metodo", "GET").upper(), "caminho": e["caminho"], "descricao": str(e.get("descricao", ""))[:200],
                           "risco": e.get("risco", "V" if e.get("metodo", "GET").upper() == "GET" else "A"), "parametros": e.get("parametros", {})} for e in eps]}


class Conectores:
    def __init__(self, pasta: Path | None = None):
        self.pasta = pasta or PASTA
        self.pasta.mkdir(exist_ok=True)

    def listar(self) -> list[dict]:
        return [json.loads(f.read_text(encoding="utf-8")) for f in sorted(self.pasta.glob("*.json"))]

    def obter(self, nome: str) -> dict:
        f = self.pasta / f"{nome}.json"
        if not NOME_OK.match(nome) or not f.exists():
            raise ErroConector(f"conector '{nome}' não existe. Existentes: {[c['nome'] for c in self.listar()]}")
        return json.loads(f.read_text(encoding="utf-8"))

    def salvar(self, d: dict) -> dict:
        v = validar(d)
        (self.pasta / f"{v['nome']}.json").write_text(json.dumps(v, ensure_ascii=False, indent=2), encoding="utf-8")
        return v

    def endpoint(self, conector: str, endpoint: str) -> tuple[dict, dict]:
        c = self.obter(conector)
        e = next((x for x in c["endpoints"] if x["nome"] == endpoint), None)
        if not e:
            raise ErroConector(f"endpoint '{endpoint}' não existe em '{conector}'. Existentes: {[x['nome'] for x in c['endpoints']]}")
        return c, e

    def chamar(self, conector: str, endpoint: str, parametros: dict, cliente: httpx.Client | None = None) -> str:
        c, e = self.endpoint(conector, endpoint)
        params = dict(parametros or {})
        caminho = re.sub(r"\{(\w+)\}", lambda m: urllib.parse.quote(str(params.pop(m.group(1), "")), safe=""), e["caminho"])
        url = c["base_url"] + caminho
        if not c.get("local"):
            url_publica(url)
        cab, query, auth = {"user-agent": "AlfredKit"}, {}, c["auth"]
        if auth["tipo"] != "nenhum":
            chave = segredos.obter(auth["segredo"])
            if not chave:
                raise ErroConector(f"falta a chave '{auth['segredo']}' no cofre. A pessoa deve rodar: python -m alfred chave {auth['segredo']}")
            if auth["tipo"] == "bearer":
                cab["authorization"] = f"Bearer {chave}"
            elif auth["tipo"] == "header":
                cab[auth["campo"]] = chave
            else:
                query[auth["campo"]] = chave
        corpo = None
        if e["metodo"] == "GET":
            query.update({k: v for k, v in params.items()})
        else:
            corpo = params
        with (cliente or httpx.Client(timeout=20, follow_redirects=False)) as h:
            r = h.request(e["metodo"], url, params=query or None, json=corpo, headers=cab)
        try:
            txt = json.dumps(r.json(), ensure_ascii=False)
        except ValueError:
            txt = r.text
        return f"HTTP {r.status_code}\n{txt[:6000]}"
