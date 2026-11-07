"""Canal do Telegram (sem internet): API falsa + cérebro roteirizado.  python -m pytest testes -q"""
import json
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from alfred import gate
from alfred.agente import Agente, Contexto
from alfred.cerebro import Resposta
from alfred.config import PADRAO
from alfred.memoria import Memoria
from alfred.telegram import CanalTelegram, partes

DONO, ESTRANHO = 111, 999


class ApiFalsa:
    def __init__(self):
        self.chamadas, self.fila, self.arquivos = [], [], {}

    def chamar(self, metodo, **p):
        self.chamadas.append((metodo, p))
        if metodo == "getUpdates":
            saida, self.fila = self.fila, []
            return saida
        if metodo == "sendMessage":
            return {"message_id": len(self.chamadas), "text": p.get("text")}
        return True

    def baixar(self, file_id):
        return self.arquivos[file_id]

    def enviadas(self, chat=DONO):
        return [p["text"] for m, p in self.chamadas if m == "sendMessage" and p["chat_id"] == chat]

    def com_botoes(self):
        return [p for m, p in self.chamadas if m == "sendMessage" and "reply_markup" in p]


class Falso:
    modelo, nome = "falso", "falso"

    def __init__(self, roteiro):
        self.roteiro = list(roteiro)

    def completar(self, sistema, mensagens, ferramentas):
        return self.roteiro.pop(0)

    def custo(self, r):
        return 0.0


def msg(texto=None, de=DONO, uid=[0], **extra):
    uid[0] += 1
    m = {"from": {"id": de}, "chat": {"id": de}, **extra}
    if texto is not None:
        m["text"] = texto
    return {"update_id": uid[0], "message": m}


@pytest.fixture()
def montar(tmp_path):
    gate.PARADO.clear()

    def _m(roteiro=(), dono=DONO, transcrever=None):
        cfg = json.loads(json.dumps(PADRAO))
        cfg["pastas"] = [str(tmp_path / "trabalho")]
        (tmp_path / "trabalho").mkdir(exist_ok=True)
        cfg["telegram"] = {"ativo": True, "dono_id": dono, "avisar_rotinas": True}
        ag = Agente(Contexto(cfg, Memoria(tmp_path / "m.db")), Falso(roteiro))
        api, eventos = ApiFalsa(), []
        canal = CanalTelegram(api, dono, ag, threading.Lock(), lambda t, **d: eventos.append((t, d)), transcrever, em_thread=False)
        ag.ctx.telegram = canal
        return canal, api, ag, eventos, tmp_path
    return _m


def test_sem_dono_so_informa_o_id(montar):
    canal, api, ag, _, _ = montar(dono=0)
    api.fila = [msg("oi", de=ESTRANHO)]
    canal.receber_uma_vez(0)
    assert "Seu ID do Telegram é 999" in api.enviadas(ESTRANHO)[0]
    assert ag.historico == []                       # não chamou o cérebro


def test_estranho_e_ignorado(montar):
    canal, api, ag, _, _ = montar()
    api.fila = [msg("apaga tudo", de=ESTRANHO)]
    canal.receber_uma_vez(0)
    assert api.enviadas(ESTRANHO) == [] and ag.historico == []


def test_dono_conversa_por_texto(montar):
    canal, api, ag, eventos, _ = montar([Resposta("Bom dia, Marcos!", [])])
    api.fila = [msg("bom dia")]
    canal.receber_uma_vez(0)
    assert api.enviadas()[-1] == "Bom dia, Marcos!"
    assert ("resposta", {"texto": "Bom dia, Marcos!"}) in eventos
    assert canal.ocupado.acquire(blocking=False)    # trava liberada no fim


def test_ocupado_avisa(montar):
    canal, api, _, _, _ = montar()
    canal.ocupado.acquire()
    api.fila = [msg("oi")]
    canal.receber_uma_vez(0)
    assert "outra tarefa" in api.enviadas()[-1]


def _chamada(nome, **args):
    return Resposta("", [{"id": "c1", "nome": nome, "args": args}])


def _responder_botao(canal, api, decisao):
    """Espera o pedido de confirmação aparecer e aperta o botão (como o celular faria)."""
    for _ in range(200):
        if api.com_botoes():
            break
        time.sleep(0.01)
    p = api.com_botoes()[-1]
    dado = next(b["callback_data"] for b in p["reply_markup"]["inline_keyboard"][0] if b["callback_data"].startswith(decisao + ":"))
    canal.tratar({"update_id": 0, "callback_query": {"id": "q", "from": {"id": DONO}, "data": dado, "message": {"message_id": 1, "text": "x"}}})


def test_acao_amarela_pede_botao_e_sim_executa(montar, tmp_path):
    tmp = tmp_path
    canal, api, ag, _, _ = montar([_chamada("escrever_arquivo", caminho=str(tmp / "trabalho" / "nota.txt"), conteudo="oi"), Resposta("Feito.", [])])
    t = threading.Thread(target=lambda: (api.fila.append(msg("cria a nota")), canal.receber_uma_vez(0)))
    t.start()
    _responder_botao(canal, api, "sim")
    t.join(5)
    assert (tmp / "trabalho" / "nota.txt").read_text(encoding="utf-8") == "oi"
    botoes = [b["text"] for b in api.com_botoes()[-1]["reply_markup"]["inline_keyboard"][0]]
    assert botoes[0] == "Sim" and botoes[-1] == "Não"
    assert api.enviadas()[-1] == "Feito."


def test_nao_bloqueia_e_estranho_nao_aperta_botao(montar, tmp_path):
    tmp = tmp_path
    canal, api, ag, _, _ = montar([_chamada("escrever_arquivo", caminho=str(tmp / "trabalho" / "x.txt"), conteudo="oi"), Resposta("Ok, não fiz.", [])])
    t = threading.Thread(target=lambda: (api.fila.append(msg("cria")), canal.receber_uma_vez(0)))
    t.start()
    for _ in range(200):
        if api.com_botoes():
            break
        time.sleep(0.01)
    cid = api.com_botoes()[-1]["reply_markup"]["inline_keyboard"][0][0]["callback_data"].split(":")[1]
    canal.tratar({"update_id": 0, "callback_query": {"id": "q", "from": {"id": ESTRANHO}, "data": f"sim:{cid}"}})
    assert cid in canal.pendentes                   # o clique do estranho não decidiu nada
    _responder_botao(canal, api, "nao")
    t.join(5)
    assert not (tmp / "trabalho" / "x.txt").exists()


def test_audio_e_transcrito(montar):
    canal, api, _, _, _ = montar([Resposta("Anotado.", [])], transcrever=lambda dados, nome: "lembrar de ligar pro fornecedor" if dados == b"ogg" else "")
    api.arquivos["f1"] = b"ogg"
    api.fila = [msg(voice={"file_id": "f1"})]
    canal.receber_uma_vez(0)
    assert api.enviadas()[0].startswith("Entendi: \"lembrar de ligar")
    assert api.enviadas()[-1] == "Anotado."
    assert canal.ocupado.acquire(blocking=False)


def test_audio_sem_groq_explica_e_libera(montar):
    canal, api, _, _, _ = montar()
    api.fila = [msg(voice={"file_id": "f1"})]
    canal.receber_uma_vez(0)
    assert "chave gratuita da Groq" in api.enviadas()[-1]
    assert canal.ocupado.acquire(blocking=False)


def test_parar(montar):
    canal, api, _, _, _ = montar()
    api.fila = [msg("/parar")]
    canal.receber_uma_vez(0)
    assert gate.PARADO.is_set() and api.enviadas()[-1] == "Parei."
    gate.PARADO.clear()


def test_texto_longo_vira_partes():
    p = partes("linha\n" * 2000)
    assert len(p) > 1 and all(len(x) <= 3900 for x in p)


def test_ferramenta_avisar_so_para_o_dono(montar):
    canal, api, ag, _, _ = montar()
    f = ag.registro.por_nome["telegram_avisar"]
    assert f.risco.value == "V" and f.grupo == "comunicacao"
    assert f.executar(texto="reunião às 15h") == "aviso enviado para você no Telegram"
    assert api.enviadas() == ["reunião às 15h"]


def test_rotina_chega_no_telegram(montar, monkeypatch):
    from fastapi.testclient import TestClient
    from alfred import servidor, telegram
    canal, api, ag, _, _ = montar([Resposta("Hoje: 2 compromissos.", [])])
    monkeypatch.setattr(telegram, "montar", lambda *a: canal)
    monkeypatch.setattr(canal, "iniciar", lambda parar: None)
    capturado = {}
    monkeypatch.setattr(servidor.rotinas, "iniciar", lambda executar, parar: capturado.setdefault("rodar", executar))
    app = servidor.criar_app(ag, token="tok")
    with TestClient(app, base_url="http://127.0.0.1:8765"):
        capturado["rodar"]({"nome": "bom-dia", "pedido": "bom dia"})
    assert api.enviadas()[-1] == "Hoje: 2 compromissos."


def test_desligado_nao_registra_ferramenta(tmp_path):
    cfg = json.loads(json.dumps(PADRAO))
    cfg["pastas"] = [str(tmp_path)]
    ag = Agente(Contexto(cfg, Memoria(tmp_path / "m.db")), Falso([]))
    assert "telegram_avisar" not in ag.registro.por_nome


def test_api_real_monta_urls_certas():
    import httpx
    from alfred.telegram import ApiTelegram
    vistos = []

    def tratar(req):
        vistos.append((req.method, str(req.url), req.content))
        if req.url.path.endswith("/getFile"):
            return httpx.Response(200, json={"ok": True, "result": {"file_path": "voice/f.oga"}})
        if "/file/" in req.url.path:
            return httpx.Response(200, content=b"OGG")
        if req.url.path.endswith("/sendMessage"):
            return httpx.Response(200, json={"ok": False, "description": "chat not found"})
        return httpx.Response(200, json={"ok": True, "result": []})
    api = ApiTelegram("123:ABC", httpx.Client(transport=httpx.MockTransport(tratar)))
    assert api.chamar("getUpdates", offset=5, timeout=0) == []
    assert vistos[0][1] == "https://api.telegram.org/bot123:ABC/getUpdates" and b'"offset":5' in vistos[0][2].replace(b" ", b"")
    assert api.baixar("x") == b"OGG" and vistos[-1][1] == "https://api.telegram.org/file/bot123:ABC/voice/f.oga"
    with pytest.raises(RuntimeError, match="chat not found"):
        api.chamar("sendMessage", chat_id=1, text="oi")


def test_apresentar_mostra_bot_tira_webhook_e_explica_token_errado():
    from alfred.telegram import CanalTelegram

    class Api(ApiFalsa):
        def __init__(self, ok=True):
            super().__init__()
            self.ok = ok

        def chamar(self, metodo, **p):
            self.chamadas.append((metodo, p))
            if not self.ok:
                raise RuntimeError("Telegram getMe: Unauthorized")
            return {"getMe": {"username": "alfred_marcos_bot"}, "getWebhookInfo": {"url": "https://velho"}}.get(metodo, True)
    api = Api()
    c = CanalTelegram(api, None, None, threading.Lock(), lambda *a, **k: None)
    txt = c.apresentar()
    assert "@alfred_marcos_bot" in txt and "sem dono" in txt and ("deleteWebhook", {}) in api.chamadas
    c2 = CanalTelegram(Api(ok=False), DONO, None, threading.Lock(), lambda *a, **k: None)
    assert "Unauthorized" in c2.apresentar() and "--colar" in c2.apresentar()
