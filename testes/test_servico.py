"""Serviço escondido: uma cópia só, reabre se cair (com espera crescente), /reiniciar pelo Telegram sem entrar em loop."""
import socket
import threading

from alfred import __main__ as principal
from alfred import servico


class P:
    def __init__(self, codigo):
        self.codigo = codigo

    def wait(self):
        return self.codigo


def test_vigia_reinicia_e_para():
    fila, esperas = [1, servico.REINICIAR, 0], []
    assert servico.vigiar(lambda: P(fila.pop(0)), esperas.append) == 0
    assert esperas == [5] and not fila                 # caiu (1) -> espera 5 s; pediu reinício (75) -> volta na hora; 0 -> para


def test_vigia_espera_crescente():
    esperas = []
    servico.vigiar(lambda: P(1), esperas.append, max_ciclos=6)
    assert esperas == [5, 10, 20, 40, 60, 60]


def test_trava_unica_e_porta_ocupada():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        livre = s.getsockname()[1]
    t1 = servico.trava_unica(livre)
    try:
        assert t1 is not None and servico.trava_unica(livre) is None and servico.porta_ocupada(livre)
    finally:
        t1.close()


def test_iniciar_com_alfred_ja_aberto_nao_abre_outro(monkeypatch, capsys):
    abertos = []
    monkeypatch.setattr(servico, "porta_ocupada", lambda porta, host="127.0.0.1": True)
    monkeypatch.setattr(principal.webbrowser, "open", abertos.append)
    assert principal.main([]) == 0
    assert "já está aberto" in capsys.readouterr().out and abertos and abertos[0].startswith("http://127.0.0.1:")


def test_girar_log(tmp_path):
    arq = tmp_path / "alfred.log"
    arq.write_text("x" * 50)
    servico.girar_log(arq, limite=10)
    assert not arq.exists() and (tmp_path / "alfred.log.1").exists()


def test_telegram_reiniciar(monkeypatch, tmp_path):
    from alfred import config
    from alfred.telegram import CanalTelegram
    from test_telegram import ApiFalsa, DONO
    monkeypatch.setattr(config, "DADOS", tmp_path)
    api = ApiFalsa()
    c = CanalTelegram(api, DONO, None, threading.Lock(), lambda *a, **k: None, em_thread=False)
    saidas = []
    monkeypatch.setattr(c, "sair", saidas.append)
    monkeypatch.setattr(threading, "Timer", lambda t, f: type("T", (), {"start": lambda self: f()})())
    msg = {"update_id": 41, "message": {"from": {"id": DONO}, "chat": {"id": DONO}, "text": "/reiniciar"}}
    monkeypatch.delenv("ALFRED_SERVICO", raising=False)
    c.tratar(msg)
    assert "iniciar.bat" in api.enviadas()[-1] and not saidas
    monkeypatch.setenv("ALFRED_SERVICO", "1")
    c.offset = 42
    c.tratar(msg)
    assert ("getUpdates", {"offset": 42, "timeout": 0}) in api.chamadas          # confirmou: não volta em loop
    assert saidas == [servico.REINICIAR] and (tmp_path / "reiniciado.flag").exists() and "Reiniciando" in api.enviadas()[-1]
