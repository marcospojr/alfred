"""Servidor local (só 127.0.0.1): tela de conversa, confirmações, log ao vivo, voz por navegador."""
import asyncio
import contextlib
import json
import queue
import secrets
import threading
import time
import uuid
from collections import deque
from pathlib import Path

import httpx
from fastapi import FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from . import __version__, cota, gate, rotinas, segredos
from .apps import CSP, ErroApp, GerenteApps
from .mcp_cliente import GerenteMcp
from .agente import Agente
from .config import BASE, DADOS

WEB = Path(__file__).parent / "web"


class Barramento:
    def __init__(self):
        self.filas: list[queue.Queue] = []
        self.hist: deque = deque(maxlen=300)
        self.n = 0
        self.trava = threading.Lock()

    def emitir(self, tipo: str, **dados):
        with self.trava:
            self.n += 1
            ev = {"n": self.n, "t": time.strftime("%H:%M:%S"), "tipo": tipo, **dados}
            self.hist.append(ev)
            for f in list(self.filas):
                f.put(ev)


BACKUP_AUTOMATICO = True     # os testes desligam


class PortaTailscale:
    """Deixa o painel abrir pelo Tailscale (tailscale serve), SÓ para o dono.

    O 'tailscale serve' entrega o pedido aqui no 127.0.0.1 e põe o cabeçalho Tailscale-User-Login com a conta de quem
    está acessando (ele apaga qualquer cópia falsa que venha de fora). Pela internet aberta (Funnel) esse cabeçalho não existe.
    Regra, valendo sempre (mesmo com [tailscale] desligado):
    - pedido que chegou por proxy (X-Forwarded-For), pelo endereço do Tailscale ou com Tailscale-User-Login
      -> só passa se [tailscale] ativo = true e a conta for a do dono; senão 403.
    - pedido direto do próprio PC -> segue como sempre (host 127.0.0.1 + token).
    """

    def __init__(self, app, cfg: dict):
        self.app, self.cfg = app, cfg

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        ts = self.cfg.get("tailscale", {}) or {}
        cab = {k.lower(): v for k, v in scope.get("headers", [])}
        host = cab.get(b"host", b"").decode("latin-1").split(":")[0].lower()
        login = cab.get(b"tailscale-user-login", b"").decode("latin-1").strip().lower()
        endereco = str(ts.get("endereco", "")).lower().rstrip(".")
        de_fora = b"x-forwarded-for" in cab or bool(login) or (endereco and host == endereco)
        if not de_fora:
            return await self.app(scope, receive, send)
        if not (ts.get("ativo") and login and login == str(ts.get("dono", "")).strip().lower()):
            gate.registrar({"ferramenta": "painel", "risco": "-", "acao": f"acesso de fora recusado ({login or 'sem conta do Tailscale'}, host {host})", "resultado": "estranho"})
            resp = JSONResponse({"detail": "painel do Alfred: acesso só do dono pelo Tailscale"}, status_code=403)
            return await resp(scope, receive, send)
        porta = self.cfg.get("porta", 8765)
        scope = dict(scope, headers=[(k, v) for k, v in scope["headers"] if k.lower() != b"host"] + [(b"host", f"127.0.0.1:{porta}".encode())])
        return await self.app(scope, receive, send)


def criar_app(agente: Agente | None = None, token: str | None = None) -> FastAPI:
    agente = agente or Agente()
    token = token or secrets.token_urlsafe(24)
    bus = Barramento()
    pendentes: dict[str, dict] = {}
    ocupado = threading.Lock()
    atual = {"ferramenta": None}
    parar_rotinas = threading.Event()
    agente.ctx.apps = GerenteApps(token, agente.ctx.pasta_apps)
    motor = agente.garantir_motor()
    motor.emitir = lambda tipo, **d: bus.emitir(tipo, **d)
    agente.ctx.mcp = GerenteMcp(agente.ctx)
    arq_token = DADOS / "api.token"          # lido pelo servidor MCP local (python -m alfred mcp) e por scripts seus
    arq_token.write_text(token)
    try:
        arq_token.chmod(0o600)
    except OSError:
        pass

    @contextlib.asynccontextmanager
    async def vida(_app):
        if app.state.telegram:
            app.state.telegram.iniciar(parar_rotinas)
        rotinas.iniciar(rodar_rotina, parar_rotinas)
        motor.iniciar(parar_rotinas)
        agente.ctx.mcp.iniciar()
        if BACKUP_AUTOMATICO:
            from . import backup
            backup.iniciar(parar_rotinas, bus.emitir)
        yield
        parar_rotinas.set()
        agente.ctx.mcp.parar()

    app = FastAPI(title="Alfred Kit", docs_url=None, redoc_url=None, openapi_url=None, lifespan=vida)
    app.add_middleware(PortaTailscale, cfg=agente.ctx.cfg)
    app.state.agente, app.state.token, app.state.bus, app.state.pendentes = agente, token, bus, pendentes
    from . import telegram
    app.state.telegram = agente.ctx.telegram = telegram.montar(agente, ocupado, bus.emitir)
    porta = agente.ctx.cfg["porta"]

    def checar(host: str | None, chave: str | None):
        if (host or "").split(":")[0] not in ("127.0.0.1", "localhost"):
            raise HTTPException(403, "host não permitido")
        if not secrets.compare_digest(chave or "", token):
            raise HTTPException(401, "token inválido")

    def emitir(tipo, **d):
        if tipo == "ferramenta":
            atual["ferramenta"] = d.get("nome")
        bus.emitir(tipo, **d)

    def confirmar(frase: str) -> bool:
        cid = uuid.uuid4().hex[:8]
        ev = threading.Event()
        info = {"ev": ev, "decisao": None, "ferramenta": atual["ferramenta"]}
        pendentes[cid] = info
        risco = agente.registro.por_nome[atual["ferramenta"]].risco.value if atual["ferramenta"] in agente.registro.por_nome else "R"
        bus.emitir("confirmar", id=cid, frase=frase, ferramenta=atual["ferramenta"], risco=risco)
        ev.wait(timeout=180)
        pendentes.pop(cid, None)
        d = info["decisao"]
        if d == "sempre" and risco == "A" and info["ferramenta"]:
            agente.sempre.add(info["ferramenta"])
        ok = d in ("sim", "sempre")
        bus.emitir("decisao", id=cid, ok=ok)
        return ok

    def trabalhar(texto: str, modo: str | None):
        try:
            resp = agente.responder(texto, emitir, confirmar, modo, origem="tela")
            bus.emitir("resposta", texto=resp)
        except Exception as e:
            bus.emitir("erro", texto=f"{type(e).__name__}: {e}")
        finally:
            ocupado.release()

    def rodar_rotina(r: dict):
        if not ocupado.acquire(timeout=600):   # se você estiver conversando na hora, a rotina espera (até 10 min) em vez de se perder
            bus.emitir("erro", texto=f"rotina {r['nome']} não rodou: fiquei ocupado por mais de 10 minutos")
            return
        try:
            bus.emitir("rotina", nome=r["nome"])
            hist: list = []
            resp = agente.responder(r["pedido"], emitir, lambda f: False, "observar", hist)
            bus.emitir("resposta", texto=f"[rotina {r['nome']}] {resp}")
            tg = app.state.telegram
            if tg and r.get("telegram", agente.ctx.cfg.get("telegram", {}).get("avisar_rotinas", True)):
                tg.avisar(resp)
        finally:
            ocupado.release()

    def host_ok(request: Request):
        if (request.headers.get("host") or "").split(":")[0] not in ("127.0.0.1", "localhost"):
            raise HTTPException(403, "host não permitido")

    @app.get("/apps/{nome}/{arquivo:path}")
    def servir_app(nome: str, arquivo: str, request: Request):
        host_ok(request)
        try:
            corpo, tipo = agente.ctx.apps.servir(nome, arquivo)
        except ErroApp:
            raise HTTPException(404, "app ou arquivo não encontrado")
        from fastapi.responses import Response
        return Response(corpo, media_type=tipo, headers={"Content-Security-Policy": CSP, "X-Content-Type-Options": "nosniff", "Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})

    @app.get("/api/app/{nome}/dados")
    def app_dados(nome: str, request: Request, x_app_token: str | None = Header(None)):
        host_ok(request)
        if not agente.ctx.apps.token_ok(nome, x_app_token):
            raise HTTPException(401, "token do app inválido")
        return {"dados": agente.ctx.apps.dados(nome)}

    @app.put("/api/app/{nome}/dados")
    async def app_salvar(nome: str, request: Request, x_app_token: str | None = Header(None)):
        host_ok(request)
        if not agente.ctx.apps.token_ok(nome, x_app_token):
            raise HTTPException(401, "token do app inválido")
        try:
            agente.ctx.apps.salvar_dados(nome, await request.json())
        except ErroApp as e:
            raise HTTPException(413, str(e))
        return {"ok": True}

    @app.post("/api/app/{nome}/perguntar")
    async def app_perguntar(nome: str, request: Request, x_app_token: str | None = Header(None)):
        """O app pode perguntar ao Alfred, mas só com ferramentas de LEITURA (modo observar)."""
        host_ok(request)
        if not agente.ctx.apps.token_ok(nome, x_app_token):
            raise HTTPException(401, "token do app inválido")
        texto = str((await request.json()).get("texto", ""))[:2000]
        if not ocupado.acquire(blocking=False):
            raise HTTPException(409, "estou terminando outra tarefa")
        try:
            resp = await asyncio.to_thread(agente.responder, texto, lambda *a, **k: None, lambda f: False, "observar", [], False)
        finally:
            ocupado.release()
        return {"texto": resp}

    @app.post("/api/webhook/{nome}")
    async def webhook(nome: str, request: Request):
        """Chamada externa (n8n, Zapier, Claude, outro sistema) que dispara uma automação ligada. Exige o segredo dela."""
        corpo = (await request.body()).decode("utf-8", "replace")
        codigo, msg = motor.webhook(nome, request.headers.get("x-webhook-secret", ""), corpo)
        return JSONResponse({"ok": codigo == 202, "msg": msg}, status_code=codigo)

    @app.get("/api/painel")
    def painel(request: Request, x_alfred: str | None = Header(None)):
        checar(request.headers.get("host"), x_alfred)
        from .automacoes import resumo
        return {"automacoes": [{"nome": a["nome"], "ativa": a["ativa"], "resumo": resumo(a)} for a in motor.listar()],
                "apps": [{"nome": a["nome"], "titulo": a["titulo"], "url": f"/apps/{a['nome']}/"} for a in agente.ctx.apps.listar()],
                "conectores": [{"nome": c["nome"], "endpoints": [e["nome"] for e in c["endpoints"]]} for c in (agente.ctx.conectores.listar() if agente.ctx.conectores else [])],
                "mcp": [{"nome": c["nome"], "conectado": c["nome"] in agente.ctx.mcp.clientes, "erro": agente.ctx.mcp.erros.get(c["nome"], "")} for c in agente.ctx.mcp.config()]}

    @app.post("/api/automacao/rodar")
    async def rodar_automacao(request: Request, x_alfred: str | None = Header(None)):
        """Botão 'rodar agora' do painel: é a PESSOA mandando, com as permissões da própria automação."""
        checar(request.headers.get("host"), x_alfred)
        nome = str((await request.json()).get("nome", ""))
        if not motor.obter(nome):
            raise HTTPException(404, "automação não existe")
        threading.Thread(target=motor.executar, args=(nome, "", "botão do painel"), daemon=True).start()
        return {"ok": True}

    @app.post("/api/pedir")
    async def pedir(request: Request, x_alfred: str | None = Header(None)):
        """Usado pelo servidor MCP local: quem chama (Claude Desktop/Code) pede e espera a resposta; confirmações aparecem NA TELA do Alfred."""
        checar(request.headers.get("host"), x_alfred)
        texto = str((await request.json()).get("texto", "")).strip()[:4000]
        if not texto:
            raise HTTPException(400, "texto vazio")
        if not ocupado.acquire(blocking=False):
            raise HTTPException(409, "estou terminando outra tarefa")
        bus.emitir("usuario", texto=texto + "  (pedido vindo de outro programa)")
        res: dict = {}

        def rodar():
            try:
                res["texto"] = agente.responder(texto, emitir, confirmar, None)
                bus.emitir("resposta", texto=res["texto"])
            except Exception as e:
                res["texto"] = f"erro: {e}"
            finally:
                ocupado.release()
        th = threading.Thread(target=rodar, daemon=True)
        th.start()
        await asyncio.to_thread(th.join, 175)
        return {"texto": res.get("texto", "ainda trabalhando; veja a tela do Alfred")}

    @app.get("/", response_class=HTMLResponse)
    def inicio(request: Request):
        if (request.headers.get("host") or "").split(":")[0] not in ("127.0.0.1", "localhost"):
            raise HTTPException(403, "host não permitido")
        html = (WEB / "index.html").read_text(encoding="utf-8").replace("__TOKEN__", token).replace("__NOME__", agente.ctx.cfg["nome"])
        return HTMLResponse(html, headers={"Cache-Control": "no-store"})

    @app.get("/api/estado")
    def estado(request: Request, x_alfred: str | None = Header(None)):
        checar(request.headers.get("host"), x_alfred)
        c = agente.ctx.cfg
        try:
            modelo = agente.provedor.modelo
            chave_ok = True
        except Exception as e:
            modelo, chave_ok = str(e), False
        return {"versao": __version__, "nome": c["nome"], "modo": c["modo"], "provedor": c["provedor"], "modelo": modelo, "cerebro_pronto": chave_ok,
                "ferramentas": agente.registro.lista(), "gasto_hoje": round(gate._gasto_hoje["usd"], 4), "limite": gate.LIMITE_DIARIO_USD, "ocupado": ocupado.locked(),
                "cota": cota.estado()}

    @app.post("/api/mensagem")
    async def mensagem(request: Request, x_alfred: str | None = Header(None)):
        checar(request.headers.get("host"), x_alfred)
        corpo = await request.json()
        texto = str(corpo.get("texto", "")).strip()[:4000]
        modo = corpo.get("modo") if corpo.get("modo") in ("observar", "supervisionado", "liberado") else None
        if not texto:
            raise HTTPException(400, "texto vazio")
        if not ocupado.acquire(blocking=False):
            raise HTTPException(409, "estou terminando outra tarefa")
        bus.emitir("usuario", texto=texto)
        threading.Thread(target=trabalhar, args=(texto, modo), daemon=True).start()
        return {"ok": True}

    @app.post("/api/confirmar")
    async def api_confirmar(request: Request, x_alfred: str | None = Header(None)):
        checar(request.headers.get("host"), x_alfred)
        c = await request.json()
        info = pendentes.get(c.get("id"))
        if not info:
            raise HTTPException(404, "pedido de confirmação não existe mais")
        info["decisao"] = c.get("decisao") if c.get("decisao") in ("sim", "sempre", "nao") else "nao"
        info["ev"].set()
        return {"ok": True}

    @app.post("/api/parar")
    def parar(request: Request, x_alfred: str | None = Header(None)):
        checar(request.headers.get("host"), x_alfred)
        gate.PARADO.set()
        for info in list(pendentes.values()):
            info["decisao"] = "nao"
            info["ev"].set()
        bus.emitir("parado")
        return {"ok": True}

    @app.get("/api/eventos")
    async def eventos(request: Request, t: str = "", desde: int = 0):
        checar(request.headers.get("host"), t)
        f: queue.Queue = queue.Queue()
        for ev in list(bus.hist):
            if ev["n"] > desde:
                f.put(ev)
        bus.filas.append(f)

        async def gerar():
            try:
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        ev = f.get_nowait()
                        yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
                    except queue.Empty:
                        yield ": ping\n\n"
                        await asyncio.sleep(0.4)
            finally:
                bus.filas.remove(f)
        return StreamingResponse(gerar(), media_type="text/event-stream", headers={"Cache-Control": "no-store"})

    @app.post("/api/transcrever")
    async def transcrever(request: Request, arquivo: UploadFile = File(...), x_alfred: str | None = Header(None)):
        checar(request.headers.get("host"), x_alfred)
        chave = segredos.obter("groq")
        if not chave:
            raise HTTPException(400, "voz por microfone usa a transcrição gratuita da Groq: rode python -m alfred chave groq")
        dados = await arquivo.read()
        if len(dados) > 10_000_000:
            raise HTTPException(413, "áudio grande demais")
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.post("https://api.groq.com/openai/v1/audio/transcriptions", headers={"authorization": f"Bearer {chave}"},
                             data={"model": "whisper-large-v3-turbo", "language": "pt", "response_format": "json"},
                             files={"file": (arquivo.filename or "audio.webm", dados, arquivo.content_type or "audio/webm")})
        if r.status_code != 200:
            raise HTTPException(502, f"transcrição falhou: {r.text[:200]}")
        return {"texto": r.json().get("text", "").strip()}

    return app
