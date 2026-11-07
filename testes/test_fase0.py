"""Fase 0: o comando 'python -m alfred oi' faz uma chamada real e mostra custo, sem nunca imprimir a chave."""
from alfred import __main__ as principal
from alfred import cerebro, config
from test_tudo import ctx  # noqa: F401  (fixture)


class RespHTTP:
    def __init__(self, dados, status=200):
        self._d, self.status_code, self.headers = dados, status, {}
        self.text = dados if isinstance(dados, str) else str(dados)
        self.content = self.text.encode()

    def json(self):
        return self._d


def _cfg(monkeypatch):
    base = config.carregar()
    monkeypatch.setattr(config, "carregar", lambda: {**base, "provedor": "anthropic", "modelo": "claude-sonnet-5-5"})
    monkeypatch.setattr(cerebro.segredos, "obter", lambda nome: "CHAVE-SECRETA-TESTE")


def test_oi_responde_e_mostra_custo_sem_vazar_chave(monkeypatch, capsys):
    _cfg(monkeypatch)
    visto = {}

    def post(url, headers, json, timeout):
        visto.update(url=url, corpo=json)
        return RespHTTP({"content": [{"type": "text", "text": "Oi, Marcos!"}], "stop_reason": "end_turn",
                         "usage": {"input_tokens": 20, "output_tokens": 6}})
    monkeypatch.setattr(cerebro.httpx, "post", post)
    assert principal.main(["oi"]) == 0
    saida = capsys.readouterr().out
    assert "Oi, Marcos!" in saida and "US$" in saida and "CHAVE-SECRETA-TESTE" not in saida
    assert visto["url"].endswith("/v1/messages") and "temperature" not in visto["corpo"]


def test_oi_erro_401_diz_como_corrigir(monkeypatch, capsys):
    _cfg(monkeypatch)
    monkeypatch.setattr(cerebro.httpx, "post", lambda url, headers, json, timeout: RespHTTP({"error": "invalid x-api-key"}, 401))
    assert principal.main(["oi"]) == 1
    saida = capsys.readouterr().out
    assert "chave" in saida and "python -m alfred chave anthropic" in saida and "CHAVE-SECRETA-TESTE" not in saida


def test_windows_embutidos_rodam_pelo_cmd_e_encadeamento_do_cmd_bloqueado(ctx, monkeypatch):
    """No Windows, 'echo' e 'dir' só existem dentro do cmd; & ^ % encadeiam ou expandem no cmd e são barrados."""
    from alfred.agente import Agente
    from alfred.tools import sistema
    from test_tudo import Falso
    visto = {}

    class R:
        returncode, stdout, stderr = 0, "oi\n", ""

    def run(args, **kw):
        visto["args"] = args
        return R()
    monkeypatch.setattr(sistema, "WIN", True)
    monkeypatch.setattr(sistema.subprocess, "run", run)
    ag = Agente(ctx, Falso([]))
    for cmd in ("echo oi & del x", "echo %USERPROFILE%", "echo oi ^& del x", "echo oi\ndel x"):
        r = ag.registro.executar("executar_comando", {"comando": cmd}, lambda f: True, "supervisionado", set())
        assert not r["ok"], cmd
    r = ag.registro.executar("executar_comando", {"comando": "echo oi"}, lambda f: True, "supervisionado", set())
    assert r["ok"] and visto["args"] == ["cmd", "/d", "/c", "echo", "oi"]


def test_diagnostico_acha_caractere_invisivel_e_modelo_sem_mostrar_chave(monkeypatch, capsys):
    base = config.carregar()
    monkeypatch.setattr(config, "carregar", lambda: {**base, "provedor": "groq", "modelo": ""})
    monkeypatch.setattr(cerebro.segredos, "obter", lambda nome: "gsk_SEGREDO123\x16")
    monkeypatch.setattr(cerebro.httpx, "post", lambda url, headers, json, timeout: RespHTTP("", 400))
    monkeypatch.setattr(cerebro.httpx, "get", lambda url, headers, timeout: RespHTTP({"data": [{"id": "openai/gpt-oss-120b"}]}))
    assert principal.main(["oi"]) == 1
    saida = capsys.readouterr().out
    assert "invisível" in saida and "disponível: sim" in saida and "SEGREDO123" not in saida


def test_chave_recusa_ctrl_v_e_aceita_colar(monkeypatch, capsys):
    from alfred import segredos
    guardado = {}
    monkeypatch.setattr(segredos, "guardar", lambda n, v: guardado.update({n: v}))
    monkeypatch.setattr(segredos.getpass, "getpass", lambda msg: "\x16")
    assert segredos.cli(["groq"]) == 1 and not guardado
    assert "NÃO guardei" in capsys.readouterr().out
    monkeypatch.setattr(segredos, "_area_de_transferencia", lambda: "gsk_" + "x" * 40 + "\n")
    monkeypatch.setattr(segredos, "_limpar_area_de_transferencia", lambda: None)
    assert segredos.cli(["groq", "--colar"]) == 0 and guardado["groq"] == "gsk_" + "x" * 40
    saida = capsys.readouterr().out
    assert "guardada" in saida and "xxxx" not in saida
    monkeypatch.setattr(segredos, "_area_de_transferencia", lambda: "sk-ant-errada" + "y" * 30)
    assert segredos.cli(["groq", "--colar"]) == 1


def test_fase1_sem_internet_da_erro_claro_e_nao_trava(monkeypatch, tmp_path):
    """Portão da Fase 1: erro de rede vira mensagem clara e o Alfred continua atendendo depois."""
    import httpx
    from fastapi.testclient import TestClient
    from alfred.agente import Agente, Contexto
    from alfred.memoria import Memoria
    from alfred.servidor import criar_app
    import json as _json
    cfg = _json.loads(_json.dumps(config.PADRAO))
    cfg["pastas"] = [str(tmp_path / "trabalho")]
    (tmp_path / "trabalho").mkdir()
    ag = Agente(Contexto(cfg, Memoria(tmp_path / "m.db")))
    ag._provedor = cerebro.Provedor("groq", chave="k")
    monkeypatch.setattr(cerebro.time, "sleep", lambda s: None)
    tentativas = []

    def sem_rede(url, headers, json, timeout):
        tentativas.append(1)
        raise httpx.ConnectError("getaddrinfo failed")
    monkeypatch.setattr(cerebro.httpx, "post", sem_rede)
    app = criar_app(ag, token="tok")
    with TestClient(app, base_url="http://127.0.0.1:8765") as c:
        r = c.post("/api/pedir", json={"texto": "oi"}, headers={"x-alfred": "tok"}).json()["texto"]
        assert "sem conexão" in r and "internet" in r and len(tentativas) == 3
        monkeypatch.setattr(cerebro.httpx, "post", lambda url, headers, json, timeout: RespHTTP(
            {"choices": [{"message": {"content": "voltei"}}], "usage": {}}))
        assert c.post("/api/pedir", json={"texto": "oi"}, headers={"x-alfred": "tok"}).json()["texto"] == "voltei"
