"""Contador da cota: lê os cabeçalhos da Groq, soma os tokens do dia, avisa em 80% e 95% (uma vez cada)."""
from alfred import cerebro, cota


class RespHTTP:
    status_code = 200
    text = ""

    def __init__(self, dados, cab):
        self._d, self.headers = dados, cab

    def json(self):
        return self._d


def test_cabecalhos_e_soma_do_dia():
    cab = {"x-ratelimit-limit-requests": "1000", "x-ratelimit-remaining-requests": "998",
           "x-ratelimit-limit-tokens": "8000", "x-ratelimit-remaining-tokens": "5200"}
    assert cota.registrar("groq", "openai/gpt-oss-120b", cab, 2000, 500) is None
    cota.registrar("groq", "openai/gpt-oss-120b", cab, 1000, 100)
    m = cota.estado()["modelos"]["groq/openai/gpt-oss-120b"]
    assert m["tokens"] == 3600 and m["pedidos"] == 2 and m["pedidos_restantes_dia"] == 998 and m["tokens_livres_minuto"] == 5200
    assert m["tokens_limite_dia"] == 200_000
    texto = cota.resumo()
    assert "3.600 tokens de 200.000" in texto and "pedidos restantes hoje: 998 de 1000" in texto


def test_aviso_em_80_e_95_uma_vez():
    assert cota.registrar("groq", "m", {}, 150_000, 0) is None
    a = cota.registrar("groq", "m", {}, 12_000, 0)
    assert a and "81%" in a
    assert cota.registrar("groq", "m", {}, 1_000, 0) is None
    assert "96%" in cota.registrar("groq", "m", {}, 30_000, 0)
    assert cota.registrar("groq", "m", {}, 10, 0) is None


def test_laco_registra_e_painel_mostra(monkeypatch, tmp_path):
    import json
    from fastapi.testclient import TestClient
    from alfred.agente import Agente, Contexto
    from alfred.config import PADRAO
    from alfred.memoria import Memoria
    from alfred.servidor import criar_app
    cfg = json.loads(json.dumps(PADRAO))
    cfg["pastas"] = [str(tmp_path / "t")]
    (tmp_path / "t").mkdir()
    ag = Agente(Contexto(cfg, Memoria(tmp_path / "m.db")))
    ag._provedor = cerebro.Provedor("groq", chave="k")
    monkeypatch.setattr(cerebro.httpx, "post", lambda url, headers, json, timeout: RespHTTP(
        {"choices": [{"message": {"content": "oi"}}], "usage": {"prompt_tokens": 90, "completion_tokens": 10}},
        {"x-ratelimit-remaining-requests": "999", "x-ratelimit-limit-requests": "1000"}))
    app = criar_app(ag, token="tok")
    with TestClient(app, base_url="http://127.0.0.1:8765") as c:
        assert c.post("/api/pedir", json={"texto": "oi"}, headers={"x-alfred": "tok"}).json()["texto"] == "oi"
        m = c.get("/api/estado", headers={"x-alfred": "tok"}).json()["cota"]["modelos"]["groq/openai/gpt-oss-120b"]
        assert m["tokens"] == 100 and m["pedidos_restantes_dia"] == 999


def test_telegram_cota():
    import threading
    from alfred.telegram import CanalTelegram
    from test_telegram import ApiFalsa, DONO
    cota.registrar("groq", "openai/gpt-oss-120b", {}, 500, 0)
    api = ApiFalsa()
    c = CanalTelegram(api, DONO, None, threading.Lock(), lambda *a, **k: None, em_thread=False)
    c.tratar({"update_id": 1, "message": {"from": {"id": DONO}, "chat": {"id": DONO}, "text": "/cota"}})
    assert "500 tokens de 200.000" in api.enviadas()[-1]


def test_limite_diario_do_config_vale(tmp_path, monkeypatch):
    import json
    from alfred import gate
    from alfred.agente import Agente, Contexto
    from alfred.config import PADRAO
    from alfred.memoria import Memoria
    monkeypatch.setattr(gate, "LIMITE_DIARIO_USD", 2.0)
    cfg = json.loads(json.dumps(PADRAO))
    cfg["limite_diario_usd"] = 0.20
    Agente(Contexto(cfg, Memoria(tmp_path / "m.db")))
    assert gate.LIMITE_DIARIO_USD == 0.20
