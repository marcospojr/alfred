"""Claude Code pelo Alfred: travas no comando, assinatura (sem chave de API), limite diário, contador e proibição em automação."""
import json

import pytest

from alfred import automacoes, cota
from alfred.gate import Risco
from alfred.tools import delegar
from test_tudo import ctx  # noqa: F401  (fixture)

SAIDA_REAL = json.dumps({"result": "Criei ok.txt.", "total_cost_usd": 0.0343, "is_error": False,
                         "usage": {"input_tokens": 2, "output_tokens": 26, "cache_creation_input_tokens": 7184, "cache_read_input_tokens": 0},
                         "permission_denials": [{"tool_name": "Read", "tool_input": {"file_path": "/fora.txt"}}]})


class Proc:
    def __init__(self, out, code=0):
        self.stdout, self.stderr, self.returncode = out, "", code


@pytest.fixture()
def ferramentas(ctx, monkeypatch):
    monkeypatch.setattr(delegar, "achar_claude", lambda: "/bin/claude")
    vistos = []

    def run(cmd, **kw):
        vistos.append((cmd, kw))
        return Proc(SAIDA_REAL)
    monkeypatch.setattr(delegar.subprocess, "run", run)
    fs = {f.nome: f for f in delegar.criar(ctx)}
    return fs, vistos


def test_comando_tem_travas_e_consulta_so_le():
    c = delegar.montar_comando("claude", "oi", pode_editar=False)
    assert "--restricted" in c and "--strict-mcp-config" in c and "Bash,PowerShell" in c
    assert c[c.index("--tools") + 1] == "Read,Grep,Glob,WebSearch,WebFetch" and c[c.index("--permission-mode") + 1] == "dontAsk"
    t = delegar.montar_comando("claude", "oi", pode_editar=True)
    assert "Edit" in t[t.index("--tools") + 1] and "Bash" not in t[t.index("--tools") + 1]
    assert "--bare" not in t          # bare não usa a assinatura


def test_ambiente_tira_chave_de_api(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-x")
    assert "ANTHROPIC_API_KEY" not in delegar.ambiente_assinatura()


def test_interpretar_saida_real():
    r = delegar.interpretar(SAIDA_REAL)
    assert r["texto"] == "Criei ok.txt." and r["tokens"] == 7212 and r["negados"] == ["Read"] and abs(r["usd"] - 0.0343) < 1e-9


def test_ferramentas_vermelhas_rodam_na_pasta_e_contam(ferramentas, ctx):
    fs, vistos = ferramentas
    assert fs["claude_consultar"].risco is Risco.VERMELHO and fs["claude_tarefa"].risco is Risco.VERMELHO
    saida = fs["claude_tarefa"].executar(tarefa="crie ok.txt")
    assert "Criei ok.txt." in saida and "bloqueado pelas travas: Read" in saida and "não é cobrado" in saida
    cmd, kw = vistos[-1]
    assert kw["cwd"] == str(ctx.cfg["pastas"][0]) and "ANTHROPIC_API_KEY" not in kw["env"]
    m = cota.estado()["modelos"]["claude-code/assinatura"]
    assert m["pedidos"] == 1 and m["tokens"] == 7212 and m["usd_estimado"] == 0.0343
    assert "claude-code/assinatura" in cota.resumo()


def test_limite_diario(ferramentas, ctx):
    fs, _ = ferramentas
    ctx.cfg["claude_code"] = {"limite_dia": 1}
    fs = {f.nome: f for f in delegar.criar(ctx)}
    fs["claude_consultar"].executar(pergunta="a")
    with pytest.raises(PermissionError):
        fs["claude_consultar"].executar(pergunta="b")


def test_pasta_fora_recusada(ferramentas):
    fs, vistos = ferramentas
    with pytest.raises(PermissionError):
        fs["claude_tarefa"].executar(tarefa="x", pasta="C:/Windows" if delegar.sys.platform.startswith("win") else "/etc")
    assert not vistos


def test_nunca_em_automacao(ferramentas, ctx):
    from alfred.agente import Agente
    from test_tudo import Falso
    ag = Agente(ctx, Falso([]))
    for f in delegar.criar(ctx):
        ag.registro.adicionar(f)
    base = {"nome": "x", "gatilho": {"tipo": "manual"}}
    with pytest.raises(automacoes.ErroAutomacao):
        automacoes.validar({**base, "passos": [{"ferramenta": "claude_consultar", "args": {"pergunta": "oi"}}], "permite": ["claude_consultar"]}, ag.registro)
    with pytest.raises(automacoes.ErroAutomacao):
        automacoes.validar({**base, "passos": [{"pedido": "resuma"}], "permite": ["claude_tarefa"]}, ag.registro)


def _agente_com_claude(ctx, roteiro, liberar=True):
    from alfred.agente import Agente
    from test_tudo import Falso
    ctx.cfg["claude_code"] = {"limite_dia": 10, "consulta_sem_perguntar": liberar}
    ag = Agente(ctx, Falso(roteiro))
    for f in delegar.criar(ctx):
        ag.registro.adicionar(f)
    ag.ativos.add("claude")
    return ag


def _chamada(nome, **args):
    from alfred.cerebro import Resposta
    return Resposta("", [{"id": "c1", "nome": nome, "args": args}])


def test_consulta_liberada_so_quando_e_a_pessoa(ferramentas, ctx):
    from alfred.cerebro import Resposta
    perguntas = []
    conf = lambda frase: perguntas.append(frase) or False     # a pessoa diria "não" se perguntassem
    for origem in ("telegram", "tela"):
        ag = _agente_com_claude(ctx, [_chamada("claude_consultar", pergunta="x"), Resposta("ok")])
        ag.responder("pergunta pro claude", lambda *a, **k: None, conf, origem=origem)
        assert not perguntas, origem                           # rodou sem perguntar
    ag = _agente_com_claude(ctx, [_chamada("claude_consultar", pergunta="x"), Resposta("ok")])
    ag.responder("rotina", lambda *a, **k: None, conf)          # origem padrão = automático (automação, rotina, API)
    assert len(perguntas) == 1


def test_tarefa_sempre_pergunta_e_sem_config_consulta_pergunta(ferramentas, ctx):
    from alfred.cerebro import Resposta
    perguntas = []
    conf = lambda frase: perguntas.append(frase) or False
    ag = _agente_com_claude(ctx, [_chamada("claude_tarefa", tarefa="x"), Resposta("ok")])
    ag.responder("faça", lambda *a, **k: None, conf, origem="telegram")
    ag = _agente_com_claude(ctx, [_chamada("claude_consultar", pergunta="x"), Resposta("ok")], liberar=False)
    ag.responder("pergunte", lambda *a, **k: None, conf, origem="telegram")
    assert len(perguntas) == 2


def test_so_lista_fechada_pode_ser_pre_aprovada(ctx):
    from alfred.agente import Agente
    from test_tudo import Falso
    ag = Agente(ctx, Falso([]))
    perguntas = []
    r = ag.registro.executar("executar_comando", {"comando": "echo oi"}, lambda f: perguntas.append(f) or False, "supervisionado", {"!executar_comando"})
    assert not r["ok"] and perguntas                 # "!" não libera ferramenta fora de PRE_APROVAVEIS


def test_aviso_de_espera_no_telegram(ferramentas, ctx):
    fs, _ = ferramentas
    enviados = []

    class Tg:
        def enviar(self, t):
            enviados.append(t)
    ctx.telegram, ctx.origem = Tg(), "telegram"
    fs["claude_consultar"].executar(pergunta="x")
    assert enviados and "Consultando o Claude" in enviados[0]
    ctx.origem = "tela"
    fs["claude_consultar"].executar(pergunta="y")
    assert len(enviados) == 1
