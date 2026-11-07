"""Automações: o Alfred cria, liga e encadeia rotinas sozinho (a pessoa aprova na criação).

Uma automação é um arquivo JSON em automacoes/. Tem um GATILHO e uma lista de PASSOS.
Gatilhos: horario, intervalo, pasta, webhook, evento, manual.
Passos (exatamente uma ação por passo): ferramenta | pedido (cérebro) | avisar | chamar (outra automação) | evento.
Segurança: rodando sozinha, uma automação só usa ferramentas verdes e amarelas; ferramentas VERMELHAS só se estiverem
em "permite", que a pessoa aprova de forma explícita ao criar/ligar. Limite de execuções por hora e de profundidade.
"""
import fnmatch
import json
import re
import secrets
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path

from . import gate
from .config import BASE, DADOS
from .gate import Risco

PASTA = BASE / "automacoes"
DIAS = ["seg", "ter", "qua", "qui", "sex", "sab", "dom"]
AC_PASSO = ("ferramenta", "pedido", "avisar", "chamar", "evento")
GATILHOS = {"horario": {"hora", "dias"}, "intervalo": {"minutos"}, "pasta": {"caminho", "padrao"}, "webhook": set(), "evento": {"nome"}, "manual": set()}
CHAVES_PASSO = set(AC_PASSO) | {"args", "modo", "guardar_como", "quando", "entrada", "dados"}
CHAVES_AUTO = {"nome", "descricao", "ativa", "gatilho", "passos", "permite", "limite_por_hora", "segredo_webhook"}
NOME_OK = re.compile(r"^[a-z0-9][a-z0-9_-]{1,39}$")
MAX_PASSOS, MAX_PROFUNDIDADE = 20, 3


class ErroAutomacao(ValueError):
    pass


def validar(d: dict, registro) -> dict:
    """Valida e normaliza. Levanta ErroAutomacao com mensagem que a IA consegue corrigir."""
    if not isinstance(d, dict):
        raise ErroAutomacao("a definição deve ser um objeto JSON")
    extras = set(d) - CHAVES_AUTO
    if extras:
        raise ErroAutomacao(f"chaves desconhecidas: {sorted(extras)}. Permitidas: {sorted(CHAVES_AUTO)}")
    nome = str(d.get("nome", ""))
    if not NOME_OK.match(nome):
        raise ErroAutomacao("'nome' deve ter 2 a 40 caracteres: letras minúsculas, números, hífen ou _ (ex.: bom-dia-clientes)")
    g = d.get("gatilho") or {"tipo": "manual"}
    tipo = g.get("tipo")
    if tipo not in GATILHOS:
        raise ErroAutomacao(f"gatilho.tipo inválido: {tipo}. Use um de {sorted(GATILHOS)}")
    sobra = set(g) - {"tipo"} - GATILHOS[tipo]
    if sobra:
        raise ErroAutomacao(f"gatilho '{tipo}' não aceita {sorted(sobra)}; aceita {sorted(GATILHOS[tipo])}")
    if tipo == "horario":
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", str(g.get("hora", ""))):
            raise ErroAutomacao("gatilho horario precisa de 'hora' no formato HH:MM")
        if any(x not in DIAS for x in g.get("dias", DIAS)):
            raise ErroAutomacao(f"'dias' deve usar {DIAS}")
    if tipo == "intervalo" and not (1 <= int(g.get("minutos", 0)) <= 1440):
        raise ErroAutomacao("gatilho intervalo precisa de 'minutos' entre 1 e 1440")
    if tipo == "pasta" and not g.get("caminho"):
        raise ErroAutomacao("gatilho pasta precisa de 'caminho' (dentro das pastas permitidas)")
    if tipo == "evento" and not NOME_OK.match(str(g.get("nome", ""))):
        raise ErroAutomacao("gatilho evento precisa de 'nome' (letras minúsculas, números, hífen ou _)")
    passos = d.get("passos")
    if not isinstance(passos, list) or not (1 <= len(passos) <= MAX_PASSOS):
        raise ErroAutomacao(f"'passos' deve ser uma lista de 1 a {MAX_PASSOS} itens")
    permite = list(d.get("permite", []))
    for i, p in enumerate(passos, 1):
        if not isinstance(p, dict):
            raise ErroAutomacao(f"passo {i}: deve ser um objeto, ex.: {{\"avisar\": \"texto\"}}")
        if set(p) - CHAVES_PASSO:
            raise ErroAutomacao(f"passo {i}: chaves inválidas {sorted(set(p) - CHAVES_PASSO)}. Permitidas: {sorted(CHAVES_PASSO)}. Cada passo tem UMA ação ({list(AC_PASSO)}); o horário vai no gatilho, não no passo")
        acoes = [k for k in AC_PASSO if k in p]
        if len(acoes) != 1:
            raise ErroAutomacao(f"passo {i}: deve ter exatamente uma ação entre {list(AC_PASSO)}")
        if "ferramenta" in p:
            f = registro.por_nome.get(p["ferramenta"])
            if not f:
                raise ErroAutomacao(f"passo {i}: ferramenta '{p['ferramenta']}' não existe. Existentes: {sorted(registro.por_nome)}")
            if f.risco is Risco.VERMELHO and p["ferramenta"] not in permite:
                raise ErroAutomacao(f"passo {i}: '{p['ferramenta']}' é VERMELHA (age fora, não tem volta). Para usá-la sozinha, inclua-a em 'permite'; a pessoa vai aprovar isso por escrito")
            if not isinstance(p.get("args", {}), dict):
                raise ErroAutomacao(f"passo {i}: 'args' deve ser um objeto")
        if p.get("modo", "observar") not in ("observar", "liberado"):
            raise ErroAutomacao(f"passo {i}: 'modo' deve ser observar ou liberado")
    for i, p in enumerate(passos, 1):
        if p.get("ferramenta", "").startswith("claude_"):
            raise ErroAutomacao(f"passo {i}: o Claude Code só roda quando o Marcos pede, nunca em automação (uso individual da assinatura)")
    for t in permite:
        if t.startswith("claude_"):
            raise ErroAutomacao("o Claude Code não pode ir em 'permite': ele só roda quando o Marcos pede, nunca sozinho (uso individual da assinatura)")
        f = registro.por_nome.get(t)
        if not f or f.risco is not Risco.VERMELHO:
            raise ErroAutomacao(f"'permite' só aceita ferramentas vermelhas existentes; '{t}' não é")
    saida = {"nome": nome, "descricao": str(d.get("descricao", ""))[:300], "ativa": bool(d.get("ativa", False)), "gatilho": {"tipo": tipo, **{k: g[k] for k in GATILHOS[tipo] if k in g}},
             "passos": passos, "permite": permite, "limite_por_hora": max(1, min(int(d.get("limite_por_hora", 12)), 120)),
             "segredo_webhook": d.get("segredo_webhook") or (secrets.token_urlsafe(18) if tipo == "webhook" else "")}
    return saida


def resumo(a: dict) -> str:
    g = a["gatilho"]
    quando = {"horario": f"todo dia {', '.join(g.get('dias', DIAS))} às {g.get('hora')}", "intervalo": f"a cada {g.get('minutos')} minutos", "pasta": f"quando aparecer arquivo novo em {g.get('caminho')}",
              "webhook": "quando receber uma chamada de webhook", "evento": f"quando acontecer o evento '{g.get('nome')}'", "manual": "só quando você mandar"}[g["tipo"]]
    linhas = []
    for p in a["passos"]:
        if "ferramenta" in p:
            linhas.append(f"usar {p['ferramenta']} {json.dumps(p.get('args', {}), ensure_ascii=False)[:100]}")
        elif "pedido" in p:
            linhas.append(f"pedir ao cérebro ({p.get('modo', 'observar')}): {p['pedido'][:100]}")
        elif "avisar" in p:
            linhas.append(f"avisar: {p['avisar'][:80]}")
        elif "chamar" in p:
            linhas.append(f"chamar a automação {p['chamar']}")
        else:
            linhas.append(f"emitir o evento {p['evento']}")
    txt = f"Automação '{a['nome']}' ({'LIGADA' if a['ativa'] else 'desligada'}): {quando}. Passos: " + "; ".join(linhas) + "."
    if a.get("permite"):
        txt += f" ATENÇÃO: PODERÁ SOZINHA (sem perguntar): {', '.join(a['permite'])}."
    return txt


def _subst(valor, vars_: dict):
    if isinstance(valor, str):
        return re.sub(r"\{(\w+)\}", lambda m: str(vars_.get(m.group(1), m.group(0))), valor)
    if isinstance(valor, dict):
        return {k: _subst(v, vars_) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_subst(v, vars_) for v in valor]
    return valor


def _condicao(c: dict | None, vars_: dict) -> bool:
    if not c:
        return True
    v = str(vars_.get(c.get("var"), ""))
    if "contem" in c:
        return str(c["contem"]).lower() in v.lower()
    if "nao_contem" in c:
        return str(c["nao_contem"]).lower() not in v.lower()
    if "vazio" in c:
        return (not v.strip()) == bool(c["vazio"])
    return True


def normalizar(a: dict) -> dict:
    """Arquivos copiados à mão (dos presets, por exemplo) podem não ter todos os campos."""
    a.setdefault("descricao", "")
    a.setdefault("ativa", False)
    a.setdefault("permite", [])
    a.setdefault("limite_por_hora", 12)
    a.setdefault("segredo_webhook", "")
    a.setdefault("gatilho", {"tipo": "manual"})
    return a


class Motor:
    def __init__(self, agente, pasta: Path | None = None, emitir=None):
        self.agente = agente
        self.pasta = pasta or PASTA
        self.pasta.mkdir(exist_ok=True)
        self.emitir = emitir or (lambda tipo, **d: None)
        self.log = DADOS / "automacoes-log.jsonl"
        self.execucoes: dict[str, deque] = {}
        self.visto: dict[str, set] = {}
        self.ultimo_intervalo: dict[str, float] = {}
        self.feitas_horario: set[str] = set()
        self.trava = threading.Lock()

    # ---------- armazenamento ----------
    def listar(self) -> list[dict]:
        out = []
        for f in sorted(self.pasta.glob("*.json")):
            try:
                out.append(normalizar(json.loads(f.read_text(encoding="utf-8"))))
            except (json.JSONDecodeError, AttributeError):
                continue
        return out

    def obter(self, nome: str) -> dict | None:
        f = self.pasta / f"{nome}.json"
        return normalizar(json.loads(f.read_text(encoding="utf-8"))) if NOME_OK.match(nome) and f.exists() else None

    def salvar(self, a: dict) -> None:
        (self.pasta / f"{a['nome']}.json").write_text(json.dumps(a, ensure_ascii=False, indent=2), encoding="utf-8")

    def excluir(self, nome: str) -> bool:
        f = self.pasta / f"{nome}.json"
        if NOME_OK.match(nome) and f.exists():
            f.unlink()
            return True
        return False

    # ---------- execução ----------
    def _permissoes(self, a: dict):
        """Devolve (emitir, confirmar) para uma execução sem ninguém na frente da tela."""
        atual = {"f": None}
        permite = set(a.get("permite", []))

        def emitir(tipo, **d):
            if tipo == "ferramenta":
                atual["f"] = d.get("nome")
            self.emitir(tipo, automacao=a["nome"], **d)

        def confirmar(frase):
            return atual["f"] in permite
        return emitir, confirmar

    def executar(self, nome: str, entrada: str = "", origem: str = "manual", profundidade: int = 0, pilha: tuple = ()) -> dict:
        a = self.obter(nome)
        if not a:
            return {"ok": False, "motivo": f"automação '{nome}' não existe"}
        if profundidade > MAX_PROFUNDIDADE or nome in pilha:
            return {"ok": False, "motivo": "encadeamento circular ou fundo demais"}
        agora = time.time()
        with self.trava:
            fila = self.execucoes.setdefault(nome, deque())
            while fila and agora - fila[0] > 3600:
                fila.popleft()
            if len(fila) >= a.get("limite_por_hora", 12):
                return {"ok": False, "motivo": f"limite de {a.get('limite_por_hora', 12)} execuções por hora atingido"}
            fila.append(agora)
        vars_ = {"entrada": entrada, "agora": datetime.now().strftime("%d/%m/%Y %H:%M")}
        emitir, confirmar = self._permissoes(a)
        relato, ok = [], True
        self.emitir("automacao", nome=nome, origem=origem)
        for i, p in enumerate(a["passos"], 1):
            if gate.PARADO.is_set():
                relato.append({"passo": i, "ok": False, "resumo": "parado pela pessoa"})
                ok = False
                break
            if not _condicao(p.get("quando"), vars_):
                relato.append({"passo": i, "ok": True, "resumo": "pulado (condição falsa)"})
                continue
            try:
                if "ferramenta" in p:
                    res = self.agente.registro.executar(p["ferramenta"], _subst(p.get("args", {}), vars_), confirmar_para(confirmar, p["ferramenta"], emitir), "liberado", set())
                    saida, bom = str(res.get("saida") if res.get("ok") else res.get("motivo")), bool(res.get("ok"))
                elif "pedido" in p:
                    saida = self.agente.responder(_subst(p["pedido"], vars_), emitir, confirmar, p.get("modo", "observar"), [], registrar=False)
                    bom = True
                elif "avisar" in p:
                    saida, bom = _subst(p["avisar"], vars_), True
                    self.emitir("aviso", texto=saida, automacao=nome)
                elif "chamar" in p:
                    r = self.executar(p["chamar"], _subst(p.get("entrada", ""), vars_), f"automação {nome}", profundidade + 1, pilha + (nome,))
                    saida, bom = str(r.get("resultado") or r.get("motivo")), bool(r.get("ok"))
                else:
                    self.evento(p["evento"], str(_subst(p.get("dados", ""), vars_)), profundidade + 1, pilha + (nome,))
                    saida, bom = f"evento {p['evento']} emitido", True
            except Exception as e:
                saida, bom = f"{type(e).__name__}: {e}", False
            if p.get("guardar_como"):
                vars_[p["guardar_como"]] = saida
            vars_["ultimo"] = saida
            relato.append({"passo": i, "ok": bom, "resumo": saida[:200]})
            if not bom:
                ok = False
                break
        resultado = {"ok": ok, "resultado": vars_.get("ultimo", ""), "passos": relato}
        with self.log.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"quando": time.strftime("%Y-%m-%d %H:%M:%S"), "nome": nome, "origem": origem, "ok": ok, "passos": relato}, ensure_ascii=False) + "\n")
        self.emitir("automacao_fim", nome=nome, ok=ok, resumo=str(vars_.get("ultimo", ""))[:300])
        return resultado

    def evento(self, nome: str, dados: str = "", profundidade: int = 0, pilha: tuple = ()) -> list[str]:
        """Dispara as automações ligadas cujo gatilho é este evento."""
        disparadas = []
        for a in self.listar():
            if a.get("ativa") and a["gatilho"].get("tipo") == "evento" and a["gatilho"].get("nome") == nome:
                self.executar(a["nome"], dados, f"evento {nome}", profundidade, pilha)
                disparadas.append(a["nome"])
        return disparadas

    def webhook(self, nome: str, segredo: str, corpo: str) -> tuple[int, str]:
        a = self.obter(nome)
        if not a or not a.get("ativa") or a["gatilho"].get("tipo") != "webhook" or not secrets.compare_digest(segredo or "", a.get("segredo_webhook", "!")):
            return 404, "não encontrado"
        threading.Thread(target=self.executar, args=(nome, corpo[:8000], "webhook"), daemon=True).start()
        return 202, "aceito"

    # ---------- relógio ----------
    def tick(self, agora: datetime | None = None) -> list[str]:
        agora = agora or datetime.now()
        disparadas = []
        for a in self.listar():
            if not a.get("ativa"):
                continue
            g, nome = a["gatilho"], a["nome"]
            if g["tipo"] == "horario":
                h, m = (int(x) for x in g["hora"].split(":"))
                marca = f"{agora:%Y-%m-%d}|{nome}"
                if DIAS[agora.weekday()] in g.get("dias", DIAS) and (agora.hour, agora.minute) >= (h, m) and marca not in self.feitas_horario:
                    self.feitas_horario.add(marca)   # relógio de parede: se o Mac dormiu, roda quando acordar (no mesmo dia)
                    self.executar(nome, "", "horário")
                    disparadas.append(nome)
            elif g["tipo"] == "intervalo":
                agora_s = agora.timestamp()
                if agora_s - self.ultimo_intervalo.get(nome, 0) >= g["minutos"] * 60:
                    self.ultimo_intervalo[nome] = agora_s
                    self.executar(nome, "", "intervalo")
                    disparadas.append(nome)
            elif g["tipo"] == "pasta":
                p = Path(g["caminho"]).expanduser()
                if not p.is_dir():
                    continue
                atuais = {x.name for x in p.iterdir() if x.is_file() and fnmatch.fnmatch(x.name, g.get("padrao", "*"))}
                if nome not in self.visto:
                    self.visto[nome] = atuais   # primeira leitura: só memoriza o que já existe
                    continue
                for novo in sorted(atuais - self.visto[nome]):
                    self.executar(nome, str(p / novo), "pasta")
                    disparadas.append(nome)
                self.visto[nome] = atuais
        return disparadas

    def iniciar(self, parar: threading.Event) -> threading.Thread:
        def laco():
            while not parar.is_set():
                try:
                    self.tick()
                except Exception as e:
                    print("automações:", e)
                parar.wait(15)
        t = threading.Thread(target=laco, daemon=True, name="automacoes")
        t.start()
        return t


def confirmar_para(confirmar, nome_ferramenta: str, emitir):
    """Confirmação de uma chamada direta de ferramenta dentro da automação: só vale se estiver em 'permite'."""
    emitir("ferramenta", nome=nome_ferramenta, args={})
    return confirmar
