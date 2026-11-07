"""Agenda do Google pelo endereço secreto iCal: eventos repetidos, dia inteiro, fuso, cancelados, cópia sem internet."""
from datetime import datetime, timedelta

import pytest

from alfred.tools import agenda
from test_tudo import ctx  # noqa: F401  (fixture)

ICS = """BEGIN:VCALENDAR\r
VERSION:2.0\r
PRODID:-//Google Inc//Google Calendar 70.9054//EN\r
BEGIN:VEVENT\r
DTSTART;TZID=America/Sao_Paulo:20261102T090000\r
DTEND;TZID=America/Sao_Paulo:20261102T100000\r
RRULE:FREQ=WEEKLY;BYDAY=MO,WE\r
EXDATE;TZID=America/Sao_Paulo:20261104T090000\r
SUMMARY:Reunião semanal\r
UID:1@google.com\r
END:VEVENT\r
BEGIN:VEVENT\r
DTSTART;VALUE=DATE:20261103\r
DTEND;VALUE=DATE:20261104\r
SUMMARY:Aniversário do Pedro\r
UID:2@google.com\r
END:VEVENT\r
BEGIN:VEVENT\r
DTSTART:20261103T170000Z\r
DTEND:20261103T180000Z\r
SUMMARY:Ligação fornecedor\r
UID:3@google.com\r
END:VEVENT\r
BEGIN:VEVENT\r
DTSTART;TZID=America/Sao_Paulo:20261103T150000\r
STATUS:CANCELLED\r
SUMMARY:Cancelado\r
UID:4@google.com\r
END:VEVENT\r
END:VCALENDAR\r
"""


def test_repetidos_dia_todo_e_cancelado():
    pytest.importorskip("recurring_ical_events")
    ev = agenda._ics_completo(ICS, datetime(2026, 11, 2), datetime(2026, 11, 10))
    titulos = [(e[0].strftime("%d/%m %H:%M"), e[3]) for e in ev]
    assert ("02/11 09:00", "Reunião semanal") in titulos and ("09/11 09:00", "Reunião semanal") in titulos
    assert ("04/11 09:00", "Reunião semanal") not in titulos          # exceção (EXDATE) respeitada
    assert any(t == "Aniversário do Pedro" and e[2] for e, (_, t) in zip(ev, titulos))
    assert "Cancelado" not in [t for _, t in titulos] and "Ligação fornecedor" in [t for _, t in titulos]
    texto = agenda._formatar(ev)
    assert "02/11 (seg) 09:00–10:00  Reunião semanal" in texto and "03/11 (ter) dia todo" in texto


def test_endereco_secreto_cache_e_sem_internet(ctx, monkeypatch, tmp_path):
    import httpx
    monkeypatch.setattr(agenda, "CACHE", tmp_path / "agenda-cache.ics")
    monkeypatch.setattr("alfred.segredos.obter", lambda nome: "https://calendar.google.com/calendar/ical/x/private-abc/basic.ics" if nome == "agenda" else None)
    baixou = []

    class R:
        status_code, text = 200, ICS

        def raise_for_status(self):
            pass
    monkeypatch.setattr(httpx, "get", lambda url, **kw: baixou.append(url) or R())
    bruto, aviso = agenda._texto_ics(ctx.cfg)
    assert "VCALENDAR" in bruto and not aviso and len(baixou) == 1
    agenda._texto_ics(ctx.cfg)
    assert len(baixou) == 1                                            # usou a cópia (menos de 10 min)
    import os
    import time
    velho = time.time() - 3600
    os.utime(agenda.CACHE, (velho, velho))

    def falha(url, **kw):
        raise httpx.ConnectError("sem rede")
    monkeypatch.setattr(httpx, "get", falha)
    bruto, aviso = agenda._texto_ics(ctx.cfg)
    assert "VCALENDAR" in bruto and "sem conexão" in aviso


def test_endereco_errado_explica(ctx, monkeypatch, tmp_path):
    import httpx
    monkeypatch.setattr(agenda, "CACHE", tmp_path / "c.ics")
    monkeypatch.setattr("alfred.segredos.obter", lambda nome: "https://calendar.google.com/calendar/embed?src=x" if nome == "agenda" else None)

    class R:
        status_code, text = 200, "<html>login</html>"

        def raise_for_status(self):
            pass
    monkeypatch.setattr(httpx, "get", lambda url, **kw: R())
    with pytest.raises(RuntimeError, match="SECRETO"):
        agenda._texto_ics(ctx.cfg)


def test_sem_agenda_diz_como_configurar(ctx, monkeypatch):
    monkeypatch.setattr("alfred.segredos.obter", lambda nome: None)
    ctx.cfg["agenda_ics"] = ""
    with pytest.raises(RuntimeError, match="chave agenda --colar"):
        agenda._texto_ics(ctx.cfg)


def test_cofre_recusa_endereco_publico():
    from alfred import segredos
    assert "SECRETO" in segredos.checar("agenda", "https://calendar.google.com/calendar/embed?src=marcos%40gmail.com")
    assert segredos.checar("agenda", "https://calendar.google.com/calendar/ical/marcos%40gmail.com/private-0123456789abcdef/basic.ics") is None


ICS2 = ICS.replace("Reunião semanal", "Evento do marcospojr").replace("Aniversário do Pedro", "Outro").replace("@google.com", "@outra")


def test_varias_agendas_juntas_com_etiqueta(ctx, monkeypatch, tmp_path):
    pytest.importorskip("recurring_ical_events")
    import httpx
    monkeypatch.setattr(agenda, "CACHE", tmp_path / "agenda-cache.ics")
    enderecos = {"agenda": "https://calendar.google.com/x/private-a/basic.ics", "agenda-marcospojr": "https://calendar.google.com/y/private-b/basic.ics"}
    monkeypatch.setattr("alfred.segredos.obter", lambda n: enderecos.get(n))

    class R:
        def __init__(self, t):
            self.status_code, self.text = 200, t

        def raise_for_status(self):
            pass
    monkeypatch.setattr(httpx, "get", lambda url, **kw: R(ICS if "private-a" in url else ICS2))
    ctx.cfg["agendas"] = ["agenda", "agenda-marcospojr", "agenda-beaesthetic-gmail"]
    f = {x.nome: x for x in agenda.criar(ctx)}["agenda_hoje"]
    import datetime as dt

    class D(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 11, 2, 8, 0)
    monkeypatch.setattr(agenda, "datetime", D)
    saida = f.executar(dias=7)
    assert "Reunião semanal [principal]" in saida and "Evento do marcospojr [marcospojr]" in saida
    assert "agenda beaesthetic-gmail" in saida and "chave agenda-beaesthetic-gmail --colar" in saida     # a que falta só avisa
    assert (tmp_path / "agenda-marcospojr-cache.ics").exists()


def test_cofre_valida_agendas_extras():
    from alfred import segredos
    assert segredos.checar("agenda-marcospojr", "https://calendar.google.com/calendar/ical/x/private-abc/basic.ics") is None
    assert segredos.checar("agenda-marcospojr", "https://evil.com/private-abc") is not None


def test_icloud_publico(ctx, monkeypatch, tmp_path):
    import httpx
    from alfred import segredos
    assert segredos.checar("agenda-icloud", "webcal://p123-caldav.icloud.com/published/2/MTIzNDU2Nzg5") is None
    monkeypatch.setattr(agenda, "CACHE", tmp_path / "agenda-cache.ics")
    monkeypatch.setattr("alfred.segredos.obter", lambda n: "webcal://p123-caldav.icloud.com/published/2/abc" if n == "agenda-icloud" else None)
    urls = []

    class R:
        status_code, text = 200, ICS

        def raise_for_status(self):
            pass
    monkeypatch.setattr(httpx, "get", lambda url, **kw: urls.append(url) or R())
    bruto, _ = agenda._texto_ics(ctx.cfg, "agenda-icloud")
    assert "VCALENDAR" in bruto and urls == ["https://p123-caldav.icloud.com/published/2/abc"]
