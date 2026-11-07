"""Agenda: lê um arquivo .ics (Google, Outlook e Apple exportam) ou o Calendário do Mac; cria evento abrindo um .ics."""
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from ..config import DADOS
from ..gate import Risco
from . import Ferramenta, esquema, inteiro, texto

MAC = sys.platform == "darwin"


DIAS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
CACHE = DADOS / "agenda-cache.ics"
VALIDADE_CACHE_S = 600          # baixa a agenda de novo no máximo a cada 10 minutos


def _ics_simples(bruto: str, de: datetime, ate: datetime) -> list[tuple[datetime, datetime | None, bool, str]]:
    """Leitor de reserva (sem bibliotecas): NÃO entende eventos repetidos."""
    bruto = bruto.replace("\r\n ", "").replace("\n ", "")
    saida = []
    for bloco in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", bruto, re.S):
        ini = re.search(r"DTSTART([^:]*):(\d{8})(T(\d{6})(Z?))?", bloco)
        tit = re.search(r"SUMMARY[^:]*:(.*)", bloco)
        if not ini:
            continue
        params, d, _, h, z = ini.groups()
        dt = datetime.strptime(d + (h or "000000"), "%Y%m%d%H%M%S")
        if z:
            dt = dt + (datetime.now() - datetime.utcnow())
        if de <= dt < ate:
            saida.append((dt, None, not h, (tit.group(1).strip() if tit else "(sem título)")))
    return sorted(saida)


def _ics_completo(bruto: str, de: datetime, ate: datetime):
    """Com icalendar + recurring-ical-events: eventos repetidos, dia inteiro, fusos e exceções (EXDATE)."""
    import icalendar
    import recurring_ical_events
    cal = icalendar.Calendar.from_ical(bruto)
    saida = []
    for ev in recurring_ical_events.of(cal).between(de, ate):
        if str(ev.get("STATUS", "")).upper() == "CANCELLED":
            continue
        ini, fim = ev.decoded("DTSTART"), (ev.decoded("DTEND") if ev.get("DTEND") else None)
        dia_todo = not isinstance(ini, datetime)
        if dia_todo:
            ini = datetime(ini.year, ini.month, ini.day)
        elif ini.tzinfo:
            ini = ini.astimezone().replace(tzinfo=None)
        if isinstance(fim, datetime) and fim.tzinfo:
            fim = fim.astimezone().replace(tzinfo=None)
        saida.append((ini, fim if isinstance(fim, datetime) else None, dia_todo, str(ev.get("SUMMARY", "(sem título)")).strip()))
    return sorted(saida, key=lambda e: (e[0], not e[2]))


def _texto_ics(cfg, chave: str = "agenda") -> tuple[str, str]:
    """Devolve (conteúdo do .ics, aviso). Fonte: endereço secreto no cofre (chave) ou agenda_ics do config (arquivo ou https)."""
    from .. import segredos
    fonte = segredos.obter(chave) or (cfg.get("agenda_ics") if chave == "agenda" else "") or ""
    cache = CACHE if chave == "agenda" else CACHE.with_name(f"{chave}-cache.ics")
    if fonte.lower().startswith("webcal://"):           # link do iCloud: é o mesmo endereço em https
        fonte = "https://" + fonte[len("webcal://"):]
    if not fonte:
        raise RuntimeError(f"agenda não configurada: copie o 'endereço secreto no formato iCal' do Google Agenda e rode  python -m alfred chave {chave} --colar")
    if not fonte.lower().startswith("https://"):
        return Path(fonte).expanduser().read_text(encoding="utf-8", errors="replace"), ""
    if cache.exists() and time.time() - cache.stat().st_mtime < VALIDADE_CACHE_S:
        return cache.read_text(encoding="utf-8", errors="replace"), ""
    import httpx
    try:
        r = httpx.get(fonte, timeout=30, follow_redirects=True)
        r.raise_for_status()
        if "BEGIN:VCALENDAR" not in r.text[:2000]:
            raise RuntimeError("o endereço não devolveu uma agenda (.ics): no Google, use o endereço SECRETO no formato iCal; no iCloud, o link da Agenda Pública")
        DADOS.mkdir(exist_ok=True)
        cache.write_text(r.text, encoding="utf-8")
        return r.text, ""
    except httpx.HTTPError as e:
        if cache.exists():
            hora = datetime.fromtimestamp(cache.stat().st_mtime)
            return cache.read_text(encoding="utf-8", errors="replace"), f"(sem conexão com o Google agora; mostrando a cópia de {hora:%d/%m %H:%M})"
        raise RuntimeError(f"não consegui baixar a agenda ({type(e).__name__}); confira a internet")


def _formatar(eventos) -> str:
    linhas = []
    for ev in eventos:
        ini, fim, dia_todo, titulo = ev[:4]
        if len(ev) > 4 and ev[4]:
            titulo = f"{titulo} [{ev[4]}]"
        quando = f"{ini:%d/%m} ({DIAS[ini.weekday()]}) " + ("dia todo   " if dia_todo else f"{ini:%H:%M}" + (f"–{fim:%H:%M}" if fim and fim.date() == ini.date() else ""))
        linhas.append(f"{quando}  {titulo}")
    return "\n".join(linhas)


def criar(ctx):
    cfg = ctx.cfg

    def agenda(dias: int = 1):
        agora = datetime.now()
        de = agora.replace(hour=0, minute=0, second=0, microsecond=0)
        ate = de + timedelta(days=max(1, min(dias, 14)))
        from .. import segredos
        if not (segredos.obter("agenda") or cfg.get("agenda_ics")) and MAC:
            return _agenda_mac(dias)
        chaves = list(cfg.get("agendas") or ["agenda"])
        eventos, avisos = [], []
        for chave in chaves:
            rotulo = "" if len(chaves) == 1 else (chave.split("-", 1)[1] if "-" in chave else "principal")
            try:
                bruto, aviso = _texto_ics(cfg, chave)
            except Exception as e:
                if len(chaves) == 1:
                    raise
                avisos.append(f"(agenda {rotulo}: {e})")
                continue
            if aviso:
                avisos.append(aviso)
            try:
                evs = _ics_completo(bruto, de, ate)
            except ImportError:
                evs = _ics_simples(bruto, de, ate)
                avisos.append("(atenção: eventos que se repetem não aparecem; falta instalar icalendar e recurring-ical-events)")
            eventos += [(*e, rotulo) for e in evs]
        eventos.sort(key=lambda e: (e[0], not e[2]))
        aviso = " ".join(dict.fromkeys(avisos))
        texto_ev = _formatar(eventos) or "nenhum compromisso no período"
        return texto_ev + (f"\n{aviso}" if aviso else "")

    def _agenda_mac(dias: int):
        script = ('set d0 to current date\nset hours of d0 to 0\nset minutes of d0 to 0\nset seconds of d0 to 0\n'
                  f'set d1 to d0 + ({max(1, min(dias, 14))} * days)\nset out to ""\ntell application "Calendar"\n'
                  'repeat with c in calendars\nrepeat with e in (every event of c whose start date ≥ d0 and start date < d1)\n'
                  'set out to out & (short date string of (start date of e)) & " " & (time string of (start date of e)) & "  " & (summary of e) & linefeed\n'
                  'end repeat\nend repeat\nend tell\nreturn out')
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            raise RuntimeError("não consegui ler o Calendário (permita Automação > Calendário em Ajustes do Sistema): " + r.stderr.strip()[:200])
        return r.stdout.strip() or "nenhum compromisso no período"

    def criar_evento(titulo: str, inicio: str, duracao_min: int = 60):
        """inicio no formato 2026-10-22 15:00 (hora local). Gera um .ics e abre: a pessoa confirma a importação."""
        ini = datetime.strptime(inicio, "%Y-%m-%d %H:%M")
        fim = ini + timedelta(minutes=max(5, duracao_min))
        corpo = ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Alfred Kit//PT\r\nBEGIN:VEVENT\r\n"
                 f"UID:{int(time.time())}@alfred\r\nDTSTAMP:{datetime.utcnow():%Y%m%dT%H%M%SZ}\r\n"
                 f"DTSTART:{ini:%Y%m%dT%H%M%S}\r\nDTEND:{fim:%Y%m%dT%H%M%S}\r\nSUMMARY:{titulo}\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")
        pasta = DADOS / "eventos"
        pasta.mkdir(exist_ok=True)
        arq = pasta / f"evento-{ini:%Y%m%d-%H%M}.ics"
        arq.write_text(corpo, encoding="utf-8")
        if MAC:
            subprocess.run(["open", str(arq)], check=False)
        elif sys.platform.startswith("win"):
            import os
            os.startfile(str(arq))  # type: ignore[attr-defined]
        return f"criei {arq.name} e abri para você confirmar a importação no seu calendário"

    return [
        Ferramenta("agenda_hoje", "Lista os compromissos de hoje (ou dos próximos dias).", esquema({"dias": inteiro("quantos dias (1 a 14)")}), Risco.VERDE, agenda, lambda dias=1: f"ler a agenda ({dias} dia(s))", externo=True),
        Ferramenta("criar_evento", "Cria um evento (gera um .ics e abre no calendário para a pessoa confirmar).", esquema({"titulo": texto("título"), "inicio": texto("AAAA-MM-DD HH:MM, hora local"), "duracao_min": inteiro("duração em minutos")}, ["titulo", "inicio"]), Risco.AMARELO,
                   criar_evento, lambda titulo, inicio, duracao_min=60: f"criar o evento '{titulo}' em {inicio} ({duracao_min} min)"),
    ]
