"""Ferramentas: criar conectores de API e chamá-los (leitura livre, ação com confirmação)."""
import json

from ..conectores import Conectores, ErroConector, validar
from ..gate import Risco
from . import Ferramenta, esquema, texto


def criar(ctx):
    def c() -> Conectores:
        if ctx.conectores is None:
            ctx.conectores = Conectores(ctx.pasta_conectores)
        return ctx.conectores

    def _parse(d):
        return validar(d)

    def criar_conector(**definicao):
        v = c().salvar(definicao)
        seg = v["auth"].get("segredo")
        return f"conector '{v['nome']}' salvo com {len(v['endpoints'])} endpoint(s)." + (f" A chave '{seg}' deve ser guardada pela PESSOA: python -m alfred chave {seg}" if seg else "")

    def frase_criar(**definicao):
        try:
            v = _parse(definicao)
            return f"CRIAR conector de API '{v['nome']}' em {v['base_url']} com {len(v['endpoints'])} endpoint(s) ({', '.join(e['nome'] + '=' + e['risco'] for e in v['endpoints'])}). Chave: {v['auth'].get('segredo', 'nenhuma')}"
        except ErroConector as e:
            return f"criar conector (definição com problema, ainda será recusada: {e})"

    def listar():
        return "\n".join(f"{x['nome']} ({x['base_url']}): " + "; ".join(f"{e['nome']}[{e['metodo']} {e['risco']}] {e['descricao']}" for e in x["endpoints"]) for x in c().listar()) or "nenhum conector ainda"

    def _args(parametros) -> dict:
        if isinstance(parametros, str):
            try:
                parametros = json.loads(parametros) if parametros else {}
            except json.JSONDecodeError as e:
                raise ErroConector(f"'parametros' deve ser um objeto: {e}")
        if not isinstance(parametros, dict):
            raise ErroConector("'parametros' deve ser um objeto, ex.: {\"cep\": \"88010400\"}")
        return parametros

    def leitura(conector: str, endpoint: str, parametros: dict | str = ""):
        _, e = c().endpoint(conector, endpoint)
        if e["risco"] != "V":
            raise ErroConector(f"'{endpoint}' é de risco {e['risco']}: use conector_acao (pede confirmação)")
        return c().chamar(conector, endpoint, _args(parametros))

    def acao(conector: str, endpoint: str, parametros: dict | str = ""):
        return c().chamar(conector, endpoint, _args(parametros))

    def frase_acao(conector: str, endpoint: str, parametros: dict | str = ""):
        try:
            _, e = c().endpoint(conector, endpoint)
            return f"CHAMAR a API {conector}/{endpoint} ({e['metodo']} {e['caminho']}, risco {e['risco']}) com {(json.dumps(parametros, ensure_ascii=False) if parametros else 'sem parâmetros')[:300]}"
        except ErroConector as e:
            return f"chamar API (problema: {e})"

    P = {"conector": texto("nome do conector"), "endpoint": texto("nome do endpoint"), "parametros": texto("JSON com os parâmetros, ex.: {\"cep\": \"88010000\"}")}
    return [
        Ferramenta("conector_criar", "Registra uma API (base_url, autenticação, endpoints). Leia antes: ajuda_criar('conector'). A chave é guardada pela pessoa no cofre, nunca por você.",
                   esquema({"nome": texto("minúsculas, números, hífen ou _"), "descricao": texto("para que serve"), "base_url": texto("https://..."),
                            "auth": {"type": "object", "description": "{\"tipo\":\"nenhum\"} ou {\"tipo\":\"bearer\",\"segredo\":\"nome-no-cofre\"}"},
                            "endpoints": {"type": "array", "items": {"type": "object"}, "description": "[{\"nome\",\"metodo\",\"caminho\",\"descricao\",\"risco\"}]"}, "local": {"type": "boolean"}}, ["nome", "base_url", "endpoints"]), Risco.AMARELO, criar_conector, frase_criar, validar=lambda **d: _parse(d)),
        Ferramenta("conector_listar", "Lista as APIs conectadas e seus endpoints.", esquema(), Risco.VERDE, listar, lambda: "listar conectores"),
        Ferramenta("conector_leitura", "Chama um endpoint de LEITURA (risco V) de uma API conectada.", esquema(P, ["conector", "endpoint"]), Risco.VERDE, leitura,
                   lambda conector, endpoint, parametros="": f"ler da API {conector}/{endpoint}", externo=True),
        Ferramenta("conector_acao", "Chama um endpoint que MUDA algo (risco A ou R) de uma API conectada. Sempre confirma.", esquema(P, ["conector", "endpoint"]), Risco.VERMELHO, acao, frase_acao, externo=True),
    ]
