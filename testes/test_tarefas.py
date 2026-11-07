"""Checklist do dia: datas em português, seções, concluir/adiar/reabrir, /tarefas no Telegram e o resumo do dia numa chamada."""
import threading
from datetime import date

import pytest

from alfred.gate import Risco
from alfred.tools import tarefas as tf
from test_tudo import ctx  # noqa: F401  (fixture)

QUARTA = date(2026, 11, 4)


@pytest.mark.parametrize("entrada,esperado", [
    ("hoje", "2026-11-04"), ("amanhã", "2026-11-05"), ("amanha", "2026-11-05"), ("depois de amanhã", "2026-11-06"),
    ("sexta", "2026-11-06"), ("sexta-feira", "2026-11-06"), ("quarta", "2026-11-11"), ("segunda", "2026-11-09"),
    ("15/11", "2026-11-15"), ("02/01", "2027-01-02"), ("15/11/2026", "2026-11-15"), ("2026-12-01", "2026-12-01"), ("", None)])
def test_datas(entrada, esperado):
    assert tf.interpretar_dia(entrada, QUARTA) == esperado


def test_data_ruim_explica():
    with pytest.raises(ValueError, match="não entendi"):
        tf.interpretar_dia("semana que vem talvez", QUARTA)


def test_checklist_secoes(tmp_path):
    t = tf.Tarefas(tmp_path / "t.db")
    a = t.adicionar("pagar fornecedor", "2026-11-02")
    b = t.adicionar("ligar contador", "2026-11-04")
    t.adicionar("organizar estoque", None)
    t.adicionar("reunião atacado", "2026-11-08")
    t.adicionar("longe", "2026-12-20")
    t.marcar(b, True)
    texto = tf.checklist(t, QUARTA)
    assert "Atrasadas (1)" in texto and f"#{a} pagar fornecedor (era 02/11 (seg))" in texto
    assert "Sem data (1)" in texto and "08/11 (dom) reunião atacado" in texto and "longe" not in texto
    assert "Hoje (" not in texto                      # a única de hoje já foi feita


def test_ferramentas_riscos_e_fluxo(ctx, monkeypatch):
    fs = {f.nome: f for f in tf.criar(ctx)}
    assert fs["tarefas_listar"].risco is Risco.VERDE and fs["tarefa_adicionar"].risco is Risco.AMARELO and fs["resumo_do_dia"].risco is Risco.VERDE
    r = fs["tarefa_adicionar"].executar(tarefa="mandar orçamento", dia="hoje")
    assert "anotei #1" in r
    assert "mandar orçamento" in fs["tarefas_listar"].executar()
    assert "feito ✓ #1" in fs["tarefa_concluir"].executar(numero=1)
    assert "Feitas hoje (1)" in fs["tarefas_listar"].executar()
    assert "reabri" in fs["tarefa_reabrir"].executar(numero=1)
    assert "sem data" in fs["tarefa_adiar"].executar(numero=1, dia="sem data")
    with pytest.raises(ValueError, match="não existe"):
        fs["tarefa_concluir"].executar(numero=99)


def test_resumo_do_dia_uma_chamada_pelo_portao(ctx):
    from alfred.agente import Agente
    from alfred.tools import Ferramenta, esquema
    from test_tudo import Falso
    ag = Agente(ctx, Falso([]))
    chamados = []
    ag.registro.adicionar(Ferramenta("email_listar", "x", esquema({"conta": {"type": "string"}, "quantidade": {"type": "integer"}, "so_nao_lidos": {"type": "boolean"}}),
                                     Risco.VERDE, lambda **a: chamados.append(a) or "== contato: 1 não lido ==", lambda **a: "ler e-mails"))
    ag.registro.adicionar(Ferramenta("agenda_hoje", "x", esquema({"dias": {"type": "integer"}}), Risco.VERDE, lambda dias=1: "09:00 Reunião", lambda dias=1: "ler agenda"))
    ctx.tarefas.adicionar("ligar contador", date.today().isoformat())
    saida = ag.registro.por_nome["resumo_do_dia"].executar()
    assert "09:00 Reunião" in saida and "ligar contador" in saida and "1 não lido" in saida
    assert chamados == [{"conta": "todas", "quantidade": 3, "so_nao_lidos": True}]


def test_telegram_tarefas(ctx):
    from alfred.agente import Agente
    from alfred.telegram import CanalTelegram
    from test_telegram import ApiFalsa, DONO
    from test_tudo import Falso
    ag = Agente(ctx, Falso([]))
    ctx.tarefas.adicionar("pagar boleto", None)
    api = ApiFalsa()
    c = CanalTelegram(api, DONO, ag, threading.Lock(), lambda *a, **k: None, em_thread=False)
    c.tratar({"update_id": 1, "message": {"from": {"id": DONO}, "chat": {"id": DONO}, "text": "/tarefas"}})
    assert "pagar boleto" in api.enviadas()[-1]
