"""Automações, mini-apps, conectores de API, MCP (cliente e servidor), webhook e pedido externo."""
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from alfred import automacoes, conectores, mcp_servidor
from alfred.agente import Agente, Contexto
from alfred.apps import ErroApp, GerenteApps
from alfred.cerebro import Resposta
from alfred.config import PADRAO
from alfred.mcp_cliente import ErroMcp, GerenteMcp
from alfred.memoria import Memoria

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_tudo import Falso, chamada  # noqa: E402


@pytest.fixture()
def ag(tmp_path):
    cfg = json.loads(json.dumps(PADRAO))
    cfg["pastas"] = [str(tmp_path / "trabalho")]
    cfg["comandos_permitidos"] = ["echo"]
    (tmp_path / "trabalho").mkdir()
    ctx = Contexto(cfg, Memoria(tmp_path / "m.db"), tmp_path / "automacoes", tmp_path / "apps", tmp_path / "conectores")
    return Agente(ctx, Falso([]))


def auto(**kw):
    base = {"nome": "teste-auto", "gatilho": {"tipo": "manual"}, "passos": [{"ferramenta": "hora_atual", "guardar_como": "h"}, {"avisar": "agora é {h}"}]}
    base.update(kw)
    return base


# ---------------- automações ----------------
def test_validacao_mensagens_claras(ag):
    r = ag.registro
    for ruim, trecho in [({"nome": "A B", "passos": []}, "nome"), (auto(passos=[]), "passos"), (auto(gatilho={"tipo": "xyz"}), "gatilho.tipo"),
                         (auto(gatilho={"tipo": "horario", "hora": "25:00"}), "HH:MM"), (auto(passos=[{"ferramenta": "nao_existe"}]), "não existe"),
                         (auto(passos=[{"ferramenta": "executar_comando", "args": {"comando": "echo oi"}}]), "VERMELHA"), (auto(passos=[{"avisar": "x", "pedido": "y"}]), "exatamente uma"),
                         (auto(extra=1), "desconhecidas"), (auto(permite=["hora_atual"]), "vermelhas")]:
        with pytest.raises(automacoes.ErroAutomacao) as e:
            automacoes.validar(ruim, r)
        assert trecho in str(e.value), (ruim, str(e.value))
    ok = automacoes.validar(auto(passos=[{"ferramenta": "executar_comando", "args": {"comando": "echo oi"}}], permite=["executar_comando"]), r)
    assert ok["permite"] == ["executar_comando"] and ok["ativa"] is False        # nasce desligada


def test_executa_passos_e_variaveis(ag):
    m = ag.garantir_motor()
    m.salvar(automacoes.validar(auto(), ag.registro))
    r = m.executar("teste-auto")
    assert r["ok"] and r["resultado"].startswith("agora é ") and len(r["passos"]) == 2


def test_vermelho_so_com_permite(ag, tmp_path):
    m = ag.garantir_motor()
    passo = {"ferramenta": "executar_comando", "args": {"comando": "echo ola"}}
    m.salvar(automacoes.validar(auto(nome="com-permite", passos=[passo], permite=["executar_comando"]), ag.registro))
    assert m.executar("com-permite")["ok"]
    # mesmo arquivo editado à mão sem 'permite': o motor recusa em tempo de execução
    d = m.obter("com-permite")
    d["permite"] = []
    m.salvar(d)
    r = m.executar("com-permite")
    assert not r["ok"] and "não confirmou" in json.dumps(r, ensure_ascii=False)


def test_encadeamento_evento_e_circular(ag):
    m = ag.garantir_motor()
    m.salvar(automacoes.validar(auto(nome="primeira", passos=[{"ferramenta": "hora_atual", "guardar_como": "h"}, {"evento": "feito-1", "dados": "{h}"}]), ag.registro))
    seg = automacoes.validar(auto(nome="segunda", gatilho={"tipo": "evento", "nome": "feito-1"}, passos=[{"avisar": "recebi {entrada}"}], ativa=True), ag.registro)
    m.salvar(seg)
    avisos = []
    m.emitir = lambda tipo, **d: avisos.append((tipo, d)) if tipo == "aviso" else None
    assert m.executar("primeira")["ok"]
    assert any("recebi" in d["texto"] for t, d in avisos)
    # circular: a -> b -> a
    m.salvar(automacoes.validar(auto(nome="aa", passos=[{"chamar": "bb"}]), ag.registro))
    m.salvar(automacoes.validar(auto(nome="bb", passos=[{"chamar": "aa"}]), ag.registro))
    r = m.executar("aa")
    assert not r["ok"] and "circular" in json.dumps(r, ensure_ascii=False)


def test_condicao_e_limite_por_hora(ag):
    m = ag.garantir_motor()
    m.salvar(automacoes.validar(auto(nome="cond", limite_por_hora=2, passos=[{"avisar": "vip", "quando": {"var": "entrada", "contem": "orçamento"}}, {"avisar": "normal"}]), ag.registro))
    r = m.executar("cond", "oi")
    assert "pulado" in r["passos"][0]["resumo"]
    m.executar("cond", "x")
    assert "limite" in m.executar("cond", "y")["motivo"]


def test_passo_de_cerebro_usa_observar(ag):
    ag._provedor = Falso([chamada("escrever_arquivo", caminho="x.txt", conteudo="y"), Resposta("não consegui")])
    m = ag.garantir_motor()
    m.salvar(automacoes.validar(auto(nome="cerebro", passos=[{"pedido": "crie x.txt", "guardar_como": "r"}]), ag.registro))
    r = m.executar("cerebro")
    assert r["ok"] and r["resultado"] == "não consegui"
    assert "escrever_arquivo" not in ag._provedor.vistos[0][2]            # ferramenta de ação nem foi oferecida


def test_gatilhos_horario_pasta_intervalo(ag, tmp_path):
    m = ag.garantir_motor()
    pasta = tmp_path / "entrada"
    pasta.mkdir()
    m.salvar(automacoes.validar(auto(nome="h1", ativa=True, gatilho={"tipo": "horario", "hora": "08:00", "dias": ["qua"]}, passos=[{"avisar": "oi"}]), ag.registro))
    m.salvar(automacoes.validar(auto(nome="p1", ativa=True, gatilho={"tipo": "pasta", "caminho": str(pasta), "padrao": "*.pdf"}, passos=[{"avisar": "novo {entrada}"}]), ag.registro))
    m.salvar(automacoes.validar(auto(nome="i1", ativa=True, gatilho={"tipo": "intervalo", "minutos": 30}, passos=[{"avisar": "ping"}]), ag.registro))
    assert m.tick(datetime(2026, 10, 21, 7, 0)) == ["i1"]                       # 21/10/2026 é quarta; ainda não é 8h; intervalo dispara; pasta só memoriza
    (pasta / "a.pdf").write_text("x")
    (pasta / "b.txt").write_text("x")
    assert m.tick(datetime(2026, 10, 21, 10, 0)) == ["h1", "i1", "p1"]          # acordou às 10h: horário recuperado; PDF novo; intervalo vencido
    assert m.tick(datetime(2026, 10, 21, 10, 1)) == []                          # nada repete
    assert automacoes.DIAS[datetime(2026, 10, 22).weekday()] == "qui"


def test_webhook_exige_segredo(ag):
    m = ag.garantir_motor()
    a = automacoes.validar(auto(nome="hook", ativa=True, gatilho={"tipo": "webhook"}, passos=[{"avisar": "veio {entrada}"}]), ag.registro)
    m.salvar(a)
    assert m.webhook("hook", "errado", "x")[0] == 404
    assert m.webhook("hook", a["segredo_webhook"], "x")[0] == 202
    a["ativa"] = False
    m.salvar(a)
    assert m.webhook("hook", a["segredo_webhook"], "x")[0] == 404                # desligada


def test_ferramentas_de_automacao_pelo_portao(ag):
    ag.ativos.add("criar")
    frases = []
    ag._provedor = Falso([Resposta("", [{"id": "c1", "nome": "automacao_criar", "args": auto(nome="via-ia", passos=[{"avisar": "oi"}])}]), Resposta("criada")])
    ev = []
    ag.responder("crie uma automação", lambda t, **d: ev.append(t), lambda f: frases.append(f) or True)
    assert "CRIAR AUTOMAÇÃO" in frases[0] and "via-ia" in frases[0]
    assert ag.garantir_motor().obter("via-ia")["ativa"] is False
    ag._provedor = Falso([Resposta("", [{"id": "c2", "nome": "automacao_ativar", "args": {"nome": "via-ia", "ativa": True}}]), Resposta("ligada")])
    frases.clear()
    ag.responder("ligue", lambda t, **d: None, lambda f: frases.append(f) or False)
    assert "LIGAR" in frases[0] and ag.garantir_motor().obter("via-ia")["ativa"] is False   # vermelho recusado: continua desligada


# ---------------- mini-apps ----------------
def test_apps_criar_servir_tokens(tmp_path):
    g = GerenteApps("segredo-mestre", tmp_path / "apps")
    g.criar("lista-compras", "Compras", "<html><head><title>x</title></head><body>oi</body></html>", "teste", {"app.js": "console.log(1)"})
    corpo, tipo = g.servir("lista-compras", "")
    assert b"ALFRED_APP" in corpo and g.token("lista-compras").encode() in corpo and "html" in tipo
    assert g.token_ok("lista-compras", g.token("lista-compras")) and not g.token_ok("lista-compras", g.token("outro-app"))
    g.salvar_dados("lista-compras", {"itens": ["leite"]})
    assert g.dados("lista-compras") == {"itens": ["leite"]}
    for ruim in ("../x", "a/b", "app.json"):
        with pytest.raises(ErroApp):
            g.servir("lista-compras", ruim)
    with pytest.raises(ErroApp):
        g.criar("Ruim Nome", "t", "<p>")
    with pytest.raises(ErroApp):
        g.criar("com-exe", "t", "<p>", arquivos={"a.exe": "x"})
    g.excluir("lista-compras")
    assert not g.listar()


def test_servidor_apps_webhook_e_pedir(ag, tmp_path):
    from fastapi.testclient import TestClient
    from alfred.servidor import criar_app
    ag._provedor = Falso([Resposta("pedido feito")])
    app = criar_app(ag, token="tok")
    cab = {"x-alfred": "tok"}
    with TestClient(app, base_url="http://127.0.0.1:8765") as c:
        app.state.agente.ctx.apps.criar("meu-app", "Meu app", "<html><head></head><body>ok</body></html>")
        r = c.get("/apps/meu-app/")
        assert r.status_code == 200 and "default-src 'self'" in r.headers["content-security-policy"] and "ALFRED_APP" in r.text
        assert "tok\"" not in r.text.replace(app.state.agente.ctx.apps.token("meu-app"), "")          # token principal nunca vai para o app
        assert c.get("/apps/meu-app/", headers={"host": "evil.com"}).status_code == 403
        tk = {"x-app-token": app.state.agente.ctx.apps.token("meu-app")}
        assert c.get("/api/app/meu-app/dados", headers=tk).json() == {"dados": {}}
        assert c.put("/api/app/meu-app/dados", json={"a": 1}, headers=tk).status_code == 200
        assert c.get("/api/app/meu-app/dados", headers={"x-app-token": "errado"}).status_code == 401
        assert c.get("/api/app/meu-app/dados", headers=cab).status_code == 401            # o token principal NÃO abre a API do app
        assert c.post("/api/app/meu-app/perguntar", json={"texto": "oi"}, headers=tk).json()["texto"] == "pedido feito"
        m = app.state.agente.garantir_motor()
        a = automacoes.validar(auto(nome="hook-web", ativa=True, gatilho={"tipo": "webhook"}, passos=[{"avisar": "veio {entrada}"}]), ag.registro)
        m.salvar(a)
        assert c.post("/api/webhook/hook-web", content="oi", headers={"x-webhook-secret": "x"}).status_code == 404
        assert c.post("/api/webhook/hook-web", content="oi", headers={"x-webhook-secret": a["segredo_webhook"], "host": "meu-dominio-publico.com"}).status_code == 202
        ag._provedor = Falso([Resposta("feito pelo MCP")])
        assert c.post("/api/pedir", json={"texto": "faça"}, headers=cab).json()["texto"] == "feito pelo MCP"
        assert c.post("/api/pedir", json={"texto": "faça"}).status_code == 401
        from alfred import servidor as _srv
        assert (_srv.DADOS / "api.token").read_text(encoding="utf-8") == "tok"      # conftest aponta DADOS para uma pasta temporária


# ---------------- conectores ----------------
DEF = {"nome": "viacep", "descricao": "CEPs", "base_url": "https://viacep.com.br", "auth": {"tipo": "nenhum"},
       "endpoints": [{"nome": "buscar-cep", "metodo": "GET", "caminho": "/ws/{cep}/json/", "descricao": "endereço por CEP"},
                     {"nome": "apagar", "metodo": "DELETE", "caminho": "/x/{id}", "risco": "R"}]}


def test_conector_valida_e_chama(tmp_path, monkeypatch):
    c = conectores.Conectores(tmp_path / "c")
    for ruim in ({**DEF, "base_url": "http://x.com"}, {**DEF, "endpoints": []}, {**DEF, "auth": {"tipo": "bearer"}}, {**DEF, "extra": 1}, {**DEF, "nome": "A_B"}):
        with pytest.raises(conectores.ErroConector):
            c.salvar(ruim)
    v = c.salvar(DEF)
    assert v["endpoints"][1]["risco"] == "R" and v["endpoints"][0]["risco"] == "V"
    visto = {}

    def handler(req: httpx.Request):
        visto["url"], visto["m"] = str(req.url), req.method
        return httpx.Response(200, json={"logradouro": "Rua X"})
    monkeypatch.setattr(conectores, "url_publica", lambda u: u)
    out = c.chamar("viacep", "buscar-cep", {"cep": "88010000"}, httpx.Client(transport=httpx.MockTransport(handler)))
    assert visto["url"] == "https://viacep.com.br/ws/88010000/json/" and "Rua X" in out and out.startswith("HTTP 200")


def test_conector_chave_vem_do_cofre_e_ssrf(tmp_path, monkeypatch):
    c = conectores.Conectores(tmp_path / "c")
    c.salvar({"nome": "api-x", "base_url": "https://api.exemplo.com", "auth": {"tipo": "header", "campo": "X-API-Key", "segredo": "api-x-chave"},
              "endpoints": [{"nome": "ler", "metodo": "GET", "caminho": "/v1/ler"}]})
    monkeypatch.setattr(conectores, "url_publica", lambda u: u)
    with pytest.raises(conectores.ErroConector) as e:
        c.chamar("api-x", "ler", {})
    assert "python -m alfred chave api-x-chave" in str(e.value)
    monkeypatch.setenv("ALFRED_CHAVE_API-X-CHAVE", "SEGREDO")
    cab = {}

    def handler(req):
        cab.update(req.headers)
        return httpx.Response(200, text="ok")
    c.chamar("api-x", "ler", {}, httpx.Client(transport=httpx.MockTransport(handler)))
    assert cab["x-api-key"] == "SEGREDO"
    monkeypatch.undo()
    c.salvar({"nome": "interno", "base_url": "https://localhost", "endpoints": [{"nome": "raiz", "caminho": "/"}]})
    with pytest.raises((PermissionError, OSError)):
        c.chamar("interno", "raiz", {})


def test_ferramentas_conector_leitura_vs_acao(ag, monkeypatch):
    monkeypatch.setattr(conectores, "url_publica", lambda u: u)
    ag.ctx.conectores = conectores.Conectores(ag.ctx.pasta_conectores)
    ag.ctx.conectores.salvar(DEF)
    r = ag.registro.executar("conector_leitura", {"conector": "viacep", "endpoint": "apagar"}, lambda f: True, "supervisionado", set())
    assert not r["ok"] and "conector_acao" in r["motivo"]
    frases = []
    ag.registro.executar("conector_acao", {"conector": "viacep", "endpoint": "apagar", "parametros": "{\"id\": 1}"}, lambda f: frases.append(f) or False, "supervisionado", set())
    assert "DELETE" in frases[0] and "risco R" in frases[0]


# ---------------- MCP ----------------
def test_mcp_cliente_conecta_e_executa(ag, tmp_path):
    ger = GerenteMcp(ag.ctx, tmp_path / "mcp.json")
    d = ger.validar({"nome": "falso", "comando": sys.executable, "args": [str(Path(__file__).parent / "mcp_falso.py")], "leitura": ["somar"]})
    novas = ger.conectar(d)
    try:
        por = {f.nome: f for f in novas}
        assert set(por) == {"mcp_falso_somar", "mcp_falso_falhar"}
        assert por["mcp_falso_somar"].risco.value == "V" and por["mcp_falso_falhar"].risco.value == "A"
        assert por["mcp_falso_somar"].executar(a=2, b=3) == "5"
        with pytest.raises(ErroMcp):
            por["mcp_falso_falhar"].executar()
        ag.registro.por_nome.update(por)
        r = ag.registro.executar("mcp_falso_somar", {"a": 4, "b": 5}, lambda f: True, "supervisionado", set())
        assert r["ok"] and "9" in r["saida"] and "CONTEÚDO DE TERCEIROS" in r["saida"]
    finally:
        ger.parar()


def test_mcp_validacao_e_comando_inexistente(ag, tmp_path):
    for ruim in ({"nome": "x"}, {"nome": "a b", "comando": "npx"}, {"nome": "ok", "comando": "npx; rm -rf /"}, {"nome": "ok", "comando": "npx", "extra": 1}):
        with pytest.raises(ErroMcp):
            GerenteMcp.validar(ruim)
    ger = GerenteMcp(ag.ctx, tmp_path / "mcp.json")
    with pytest.raises(ErroMcp):
        ger.conectar({"nome": "nada", "comando": "programa-que-nao-existe-xyz", "args": []})


def test_mcp_adicionar_pelo_portao_e_so_salva_se_conectar(ag, tmp_path):
    ag.ctx.mcp = GerenteMcp(ag.ctx, tmp_path / "mcp.json")
    frases = []
    d = json.dumps({"nome": "falso", "comando": sys.executable, "args": [str(Path(__file__).parent / "mcp_falso.py")]})
    r = ag.registro.executar("mcp_adicionar", json.loads(d), lambda f: frases.append(f) or True, "supervisionado", set())
    try:
        assert r["ok"] and "INSTALAR/EXECUTAR" in frases[0] and "mcp_falso_somar" in ag.registro.por_nome
        assert ag.ctx.mcp.config()[0]["nome"] == "falso"
    finally:
        ag.ctx.mcp.parar()
    ruim = json.dumps({"nome": "quebrado", "comando": "programa-que-nao-existe-xyz"})
    r = ag.registro.executar("mcp_adicionar", json.loads(ruim), lambda f: True, "supervisionado", set())
    assert not r["ok"] and not [c for c in ag.ctx.mcp.config() if c["nome"] == "quebrado"]


def test_alfred_como_servidor_mcp(monkeypatch):
    r = mcp_servidor.tratar({"id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}})
    assert r["result"]["serverInfo"]["name"] == "alfred"
    nomes = [t["name"] for t in mcp_servidor.tratar({"id": 2, "method": "tools/list"})["result"]["tools"]]
    assert nomes == ["alfred_pedir", "alfred_estado"]
    monkeypatch.setattr(mcp_servidor, "_api", lambda c, b=None: {"texto": "feito"})
    out = mcp_servidor.tratar({"id": 3, "method": "tools/call", "params": {"name": "alfred_pedir", "arguments": {"pedido": "x"}}})
    assert out["result"]["content"][0]["text"] == "feito"
    assert mcp_servidor.tratar({"method": "notifications/initialized"}) is None
    monkeypatch.setattr(mcp_servidor, "_api", lambda c, b=None: (_ for _ in ()).throw(RuntimeError("fechado")))
    assert mcp_servidor.tratar({"id": 4, "method": "tools/call", "params": {"name": "alfred_pedir", "arguments": {}}})["result"]["isError"]


def test_ajuda_lista_temas(ag):
    r = ag.registro.executar("ajuda_criar", {"tema": "xyz"}, lambda f: True, "observar", set())
    assert r["ok"] and "automacao" in r["saida"]


def test_grupos_reduzem_ferramentas_e_habilitar_liga(ag):
    todas = {e["nome"] for e in ag.registro.esquemas("supervisionado")}
    base = {e["nome"] for e in ag.registro.esquemas("supervisionado", set())}
    assert "automacao_criar" in todas and "automacao_criar" not in base and "listar_pasta" in base and len(base) < len(todas) / 2
    r = ag.registro.executar("automacao_criar", {"nome": "xx", "gatilho": {}, "passos": []}, lambda f: True, "supervisionado", set(), set())
    assert not r["ok"] and "habilitar_grupo('criar')" in r["motivo"]
    ag._provedor = Falso([Resposta("", [{"id": "g1", "nome": "habilitar_grupo", "args": {"grupo": "criar"}}]), Resposta("", [{"id": "g2", "nome": "automacao_listar", "args": {}}]), Resposta("ok")])
    ag.responder("quero automatizar", lambda *a, **k: None, lambda f: True)
    assert "criar" in ag.ativos
    assert "automacao_listar" in ag._provedor.vistos[1][2] and "automacao_listar" not in ag._provedor.vistos[0][2]   # só aparece depois de ligar
    assert "habilitar_grupo" in ag._provedor.vistos[0][2]
    assert "criar (" in ag._provedor.vistos[0][0]                                                                   # o prompt explica os grupos


def test_argumento_invalido_volta_para_o_modelo_sem_perguntar(ag):
    ag.ativos.update({"criar"})
    perguntou = []
    r = ag.registro.executar("automacao_criar", {"nome": "ola-ok", "gatilho": {"tipo": "manual"}, "passos": [{"avisar": "a", "hora": "17:00"}]}, lambda f: perguntou.append(f) or True, "supervisionado", set(), {"criar"})
    assert not r["ok"] and "chaves inválidas" in r["motivo"] and "hora" in r["motivo"] and not perguntou
    r = ag.registro.executar("conector_criar", {"nome": "api-x", "base_url": "http://sem-https.com", "endpoints": [{"nome": "a1", "caminho": "/"}]}, lambda f: perguntou.append(f) or True, "supervisionado", set(), {"criar"})
    assert not r["ok"] and "https" in r["motivo"] and not perguntou
    ag.ctx.apps = __import__("alfred.apps", fromlist=["GerenteApps"]).GerenteApps("s", ag.ctx.pasta_apps)
    r = ag.registro.executar("app_criar", {"nome": "Nome Ruim", "titulo": "t", "html": "<p>"}, lambda f: perguntou.append(f) or True, "supervisionado", set(), {"criar"})
    assert not r["ok"] and not perguntou


def test_painel_e_rodar_automacao(ag):
    from fastapi.testclient import TestClient
    from alfred.servidor import criar_app
    app = criar_app(ag, token="tok")
    cab = {"x-alfred": "tok"}
    with TestClient(app, base_url="http://127.0.0.1:8765") as c:
        app.state.agente.garantir_motor().salvar(automacoes.validar(auto(nome="no-painel", passos=[{"avisar": "oi"}]), ag.registro))
        p = c.get("/api/painel", headers=cab).json()
        assert p["automacoes"][0]["nome"] == "no-painel" and p["apps"] == [] and p["mcp"] == []
        assert c.get("/api/painel").status_code == 401
        assert c.post("/api/automacao/rodar", json={"nome": "nao-existe"}, headers=cab).status_code == 404
        assert c.post("/api/automacao/rodar", json={"nome": "no-painel"}, headers=cab).status_code == 200
        for _ in range(60):
            if any(e["tipo"] == "automacao_fim" for e in app.state.bus.hist):
                break
            time.sleep(0.05)
        assert any(e["tipo"] == "aviso" and e["texto"] == "oi" for e in app.state.bus.hist)


def test_presets_validam_e_arquivo_copiado_a_mao_funciona(ag, tmp_path):
    import shutil
    ag.ctx.cfg["whatsapp"]["ativo"] = True
    ag.ctx.cfg["telegram"]["ativo"] = True
    ag2 = Agente(ag.ctx, Falso([]))
    base = Path(__file__).resolve().parent.parent / "presets"
    for f in sorted((base / "automacoes").glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        v = automacoes.validar(d, ag2.registro)
        assert v["ativa"] is False or d.get("ativa") is not None, f.name
    for f in sorted((base / "conectores").glob("*.json")):
        conectores.validar(json.loads(f.read_text(encoding="utf-8")))
    m = ag2.garantir_motor()
    shutil.copy(base / "automacoes" / "pdf-novo-vira-resumo.json", m.pasta / "pdf-novo-vira-resumo.json")   # sem 'permite' e sem 'limite_por_hora'
    assert "pdf-novo-vira-resumo" in automacoes.resumo(m.listar()[0])
    assert m.obter("pdf-novo-vira-resumo")["permite"] == []
