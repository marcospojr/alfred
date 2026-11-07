"""Checklist do dia: tarefas com dia opcional, guardadas em dados/tarefas.db (só no PC, fora do git).

- tarefas_listar (verde): atrasadas, de hoje, sem data, próximos dias e o que foi feito hoje.
- tarefa_adicionar / tarefa_concluir / tarefa_adiar / tarefa_reabrir (amarelas): mudam só o checklist e dá para desfazer.
- resumo_do_dia (verde): agenda de hoje + tarefas + e-mails não lidos numa chamada só (é o que o bom-dia usa;
  uma chamada só gasta bem menos da cota por minuto da Groq do que três).
"""
import re
import sqlite3
import threading
from datetime import date, datetime, timedelta

from ..config import DADOS
from ..gate import Risco
from . import Ferramenta, esquema, inteiro, texto

DIAS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
_trava = threading.Lock()


def interpretar_dia(valor: str | None, hoje: date | None = None) -> str | None:
    """'hoje', 'amanhã', 'depois de amanhã', 'sexta', '15/11', '15/11/2026', '2026-11-15' -> 'AAAA-MM-DD'. Vazio -> None."""
    hoje = hoje or date.today()
    v = (valor or "").strip().lower()
    if not v or v in ("sem data", "nenhum", "-"):
        return None
    if v == "hoje":
        return hoje.isoformat()
    if v in ("amanhã", "amanha"):
        return (hoje + timedelta(days=1)).isoformat()
    if v in ("depois de amanhã", "depois de amanha"):
        return (hoje + timedelta(days=2)).isoformat()
    nomes = {"segunda": 0, "seg": 0, "terça": 1, "terca": 1, "ter": 1, "quarta": 2, "qua": 2, "quinta": 3, "qui": 3,
             "sexta": 4, "sex": 4, "sábado": 5, "sabado": 5, "sáb": 5, "sab": 5, "domingo": 6, "dom": 6}
    chave = v.replace("-feira", "").replace(" feira", "").strip()
    if chave in nomes:
        dias = (nomes[chave] - hoje.weekday()) % 7 or 7          # o próximo, nunca hoje
        return (hoje + timedelta(days=dias)).isoformat()
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?", v)
    if m:
        d, mes, ano = int(m.group(1)), int(m.group(2)), m.group(3)
        ano = int(ano) + (2000 if ano and len(ano) == 2 else 0) if ano else hoje.year
        alvo = date(ano, mes, d)
        if not m.group(3) and alvo < hoje:
            alvo = date(ano + 1, mes, d)                          # "05/01" em dezembro = ano que vem
        return alvo.isoformat()
    try:
        return date.fromisoformat(v).isoformat()
    except ValueError:
        raise ValueError(f"não entendi a data '{valor}': use hoje, amanhã, um dia da semana, 15/11 ou 2026-11-15")


class Tarefas:
    def __init__(self, arquivo=None):
        self.arquivo = arquivo or (DADOS / "tarefas.db")
        with self._con() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS tarefas (
                id INTEGER PRIMARY KEY, texto TEXT NOT NULL, dia TEXT, criada_em TEXT DEFAULT (datetime('now','localtime')), feita_em TEXT)""")

    def _con(self):
        return sqlite3.connect(self.arquivo)

    def adicionar(self, texto_: str, dia: str | None) -> int:
        with _trava, self._con() as c:
            return c.execute("INSERT INTO tarefas (texto, dia) VALUES (?, ?)", (texto_.strip()[:300], dia)).lastrowid

    def pegar(self, id_: int):
        with self._con() as c:
            return c.execute("SELECT id, texto, dia, feita_em FROM tarefas WHERE id = ?", (id_,)).fetchone()

    def marcar(self, id_: int, feita: bool) -> None:
        with _trava, self._con() as c:
            c.execute("UPDATE tarefas SET feita_em = ? WHERE id = ?", (datetime.now().strftime("%Y-%m-%d %H:%M") if feita else None, id_))

    def mudar_dia(self, id_: int, dia: str | None) -> None:
        with _trava, self._con() as c:
            c.execute("UPDATE tarefas SET dia = ? WHERE id = ?", (dia, id_))

    def todas(self):
        with self._con() as c:
            return c.execute("SELECT id, texto, dia, feita_em FROM tarefas ORDER BY COALESCE(dia, '9999'), id").fetchall()


def _fmt_dia(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d:%d/%m} ({DIAS[d.weekday()]})"


def checklist(t: Tarefas, hoje: date | None = None, dias_frente: int = 7) -> str:
    hoje = hoje or date.today()
    h, lim = hoje.isoformat(), (hoje + timedelta(days=dias_frente)).isoformat()
    atrasadas, de_hoje, sem_data, proximas, feitas = [], [], [], [], []
    for id_, txt, dia, feita in t.todas():
        if feita:
            if feita[:10] == h:
                feitas.append(f"  ✓ #{id_} {txt}")
            continue
        if dia is None:
            sem_data.append(f"  • #{id_} {txt}")
        elif dia < h:
            atrasadas.append(f"  • #{id_} {txt} (era {_fmt_dia(dia)})")
        elif dia == h:
            de_hoje.append(f"  • #{id_} {txt}")
        elif dia <= lim:
            proximas.append(f"  • #{id_} {_fmt_dia(dia)} {txt}")
    blocos = [(f"Atrasadas ({len(atrasadas)})", atrasadas), (f"Hoje ({len(de_hoje)})", de_hoje),
              (f"Sem data ({len(sem_data)})", sem_data), (f"Próximos {dias_frente} dias ({len(proximas)})", proximas),
              (f"Feitas hoje ({len(feitas)})", feitas)]
    saida = [f"{titulo}:\n" + "\n".join(itens) for titulo, itens in blocos if itens]
    return "\n\n".join(saida) or "Nenhuma tarefa no checklist."


def criar(ctx):
    t = Tarefas(getattr(ctx, "arquivo_tarefas", None))
    ctx.tarefas = t

    def listar():
        return checklist(t)

    def adicionar(tarefa: str, dia: str = ""):
        d = interpretar_dia(dia)
        n = t.adicionar(tarefa, d)
        return f"anotei #{n}: {tarefa}" + (f" para {_fmt_dia(d)}" if d else " (sem data)")

    def _existe(id_: int):
        r = t.pegar(id_)
        if not r:
            raise ValueError(f"não existe tarefa #{id_}; veja os números com tarefas_listar")
        return r

    def concluir(numero: int):
        r = _existe(numero)
        t.marcar(numero, True)
        return f"feito ✓ #{numero} {r[1]}"

    def reabrir(numero: int):
        r = _existe(numero)
        t.marcar(numero, False)
        return f"reabri #{numero} {r[1]}"

    def adiar(numero: int, dia: str):
        r = _existe(numero)
        d = interpretar_dia(dia)
        t.mudar_dia(numero, d)
        return f"#{numero} {r[1]} agora é para " + (_fmt_dia(d) if d else "sem data")

    def resumo_do_dia():
        """Junta tudo pelo portão (só ferramentas verdes, modo observar)."""
        reg = ctx.agente.registro if getattr(ctx, "agente", None) else None
        partes = [f"Hoje é {DIAS[date.today().weekday()]}, {date.today():%d/%m/%Y}."]

        def pedir(nome, **args):
            if not reg or nome not in reg.por_nome:
                return "(não configurado)"
            r = reg.executar(nome, args, lambda f: False, "observar", set())
            return r["saida"] if r.get("ok") else f"(não consegui: {r.get('motivo')})"
        partes.append("AGENDA DE HOJE:\n" + pedir("agenda_hoje", dias=1))
        partes.append("CHECKLIST:\n" + checklist(t))
        partes.append("E-MAILS NÃO LIDOS:\n" + pedir("email_listar", conta="todas", quantidade=3, so_nao_lidos=True))
        return "\n\n".join(partes)

    return [
        Ferramenta("tarefas_listar", "Mostra o checklist: tarefas atrasadas, de hoje, sem data, dos próximos dias e feitas hoje (com o número #).", esquema(), Risco.VERDE, listar, lambda: "ver o checklist"),
        Ferramenta("tarefa_adicionar", "Anota uma tarefa no checklist. dia: hoje, amanhã, um dia da semana, 15/11 ou vazio (sem data).",
                   esquema({"tarefa": texto("o que fazer, curto"), "dia": texto("quando (opcional)")}, ["tarefa"]), Risco.AMARELO, adicionar,
                   lambda tarefa, dia="": f"anotar no checklist: {tarefa}" + (f" ({dia})" if dia else "")),
        Ferramenta("tarefa_concluir", "Marca uma tarefa como feita pelo número (#).", esquema({"numero": inteiro("número da tarefa")}, ["numero"]), Risco.AMARELO, concluir,
                   lambda numero: f"marcar a tarefa #{numero} como feita"),
        Ferramenta("tarefa_reabrir", "Desfaz o 'feito' de uma tarefa.", esquema({"numero": inteiro("número da tarefa")}, ["numero"]), Risco.AMARELO, reabrir,
                   lambda numero: f"reabrir a tarefa #{numero}"),
        Ferramenta("tarefa_adiar", "Muda o dia de uma tarefa.", esquema({"numero": inteiro("número da tarefa"), "dia": texto("novo dia (hoje, amanhã, sexta, 15/11, ou 'sem data')")}, ["numero", "dia"]), Risco.AMARELO, adiar,
                   lambda numero, dia: f"mudar a tarefa #{numero} para {dia}"),
        Ferramenta("resumo_do_dia", "Junta a agenda de hoje, o checklist e os e-mails não lidos de todas as contas numa chamada só. Use para o bom-dia ou 'como está meu dia'.", esquema(), Risco.VERDE, resumo_do_dia,
                   lambda: "montar o resumo do dia", externo=True),
    ]
