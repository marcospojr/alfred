"""Canal do Telegram: você conversa com o Alfred pelo celular (texto ou áudio) e recebe as rotinas.

Segurança:
- Só o DONO (telegram.dono_id no config.toml) é atendido. Qualquer outra pessoa é ignorada e fica no log.
- Ações amarelas e vermelhas pedem o seu "sim" com botões na própria conversa (o mesmo portão da tela).
- O token do bot fica no cofre do sistema:  python -m alfred chave telegram
- Usa a API oficial do Telegram (long polling): não abre porta nenhuma no roteador.
"""
import threading
import time
import uuid
from typing import Callable

import httpx

from . import gate

LIMITE_TEXTO = 3900          # o Telegram aceita 4096; folga para não cortar no meio
ESPERA_CONFIRMAR = 180       # segundos para você apertar Sim/Não


class ApiTelegram:
    """Fala com api.telegram.org. Trocável por um falso nos testes."""

    def __init__(self, token: str, cliente: httpx.Client | None = None):
        self._base = f"https://api.telegram.org/bot{token}"
        self._arq = f"https://api.telegram.org/file/bot{token}"
        self._c = cliente or httpx.Client(timeout=40)

    def chamar(self, metodo: str, **params):
        r = self._c.post(f"{self._base}/{metodo}", json=params)
        dados = r.json()
        if not dados.get("ok"):
            raise RuntimeError(f"Telegram {metodo}: {dados.get('description', r.status_code)}")
        return dados["result"]

    def baixar(self, file_id: str) -> bytes:
        info = self.chamar("getFile", file_id=file_id)
        r = self._c.get(f"{self._arq}/{info['file_path']}")
        r.raise_for_status()
        return r.content


def transcrever_groq(chave: str) -> Callable[[bytes, str], str]:
    """Mesma transcrição gratuita (com limite) que a tela usa. O áudio sai do computador para a Groq."""
    def transcrever(dados: bytes, nome: str) -> str:
        r = httpx.post("https://api.groq.com/openai/v1/audio/transcriptions", headers={"authorization": f"Bearer {chave}"},
                       data={"model": "whisper-large-v3-turbo", "language": "pt", "response_format": "json"},
                       files={"file": (nome, dados, "audio/ogg")}, timeout=60)
        if r.status_code != 200:
            raise RuntimeError(f"transcrição falhou: {r.text[:200]}")
        return r.json().get("text", "").strip()
    return transcrever


def partes(texto: str, limite: int = LIMITE_TEXTO) -> list[str]:
    """Quebra texto longo em pedaços, de preferência em fim de linha."""
    texto = texto.strip() or "(sem resposta)"
    saida = []
    while len(texto) > limite:
        corte = texto.rfind("\n", 0, limite)
        corte = corte if corte > limite // 2 else limite
        saida.append(texto[:corte].rstrip())
        texto = texto[corte:].lstrip()
    saida.append(texto)
    return saida


class CanalTelegram:
    def __init__(self, api, dono_id: int | None, agente, ocupado: threading.Lock, emitir_bus: Callable,
                 transcrever: Callable[[bytes, str], str] | None = None, em_thread: bool = True):
        self.api, self.dono = api, (int(dono_id) if dono_id else None)
        self.agente, self.ocupado, self.emitir_bus = agente, ocupado, emitir_bus
        self.transcrever = transcrever
        self.em_thread = em_thread          # nos testes roda tudo na mesma thread
        self.offset = 0
        self.pendentes: dict[str, dict] = {}
        self.atual = {"ferramenta": None}

    # ---------- saída ----------
    def enviar(self, texto: str, chat_id: int | None = None, **extra) -> int | None:
        destino = chat_id or self.dono
        if not destino:
            return None
        ultimo = None
        for p in partes(texto):
            msg = self.api.chamar("sendMessage", chat_id=destino, text=p, **extra)
            ultimo = msg.get("message_id") if isinstance(msg, dict) else None
            extra = {}                       # botões só na primeira parte
        return ultimo

    def avisar(self, texto: str) -> bool:
        """Usado pelas rotinas e pela ferramenta telegram_avisar: manda só para o dono."""
        if not self.dono:
            return False
        try:
            self.enviar(texto)
            return True
        except Exception as e:
            self.emitir_bus("erro", texto=f"Telegram: {e}")
            return False

    # ---------- confirmação com botões ----------
    def confirmar(self, frase: str) -> bool:
        ferramenta = self.atual["ferramenta"]
        f = self.agente.registro.por_nome.get(ferramenta)
        risco = f.risco.value if f else "R"
        cid = uuid.uuid4().hex[:8]
        info = {"ev": threading.Event(), "decisao": None}
        self.pendentes[cid] = info
        botoes = [{"text": "Sim", "callback_data": f"sim:{cid}"}]
        if risco == "A":
            botoes.append({"text": "Sempre (nesta sessão)", "callback_data": f"sempre:{cid}"})
        botoes.append({"text": "Não", "callback_data": f"nao:{cid}"})
        rotulo = "AÇÃO SEM VOLTA" if risco == "R" else "Posso fazer isto?"
        msg_id = self.enviar(f"{rotulo}\n\n{frase}", reply_markup={"inline_keyboard": [botoes]})
        self.emitir_bus("confirmar", id=cid, frase=frase + "  (respondendo pelo Telegram)", ferramenta=ferramenta, risco=risco)
        info["ev"].wait(timeout=ESPERA_CONFIRMAR)
        self.pendentes.pop(cid, None)
        d = info["decisao"]
        if d is None and msg_id:
            try:
                self.api.chamar("editMessageText", chat_id=self.dono, message_id=msg_id, text=f"{rotulo}\n\n{frase}\n\n(expirou: não fiz)")
            except Exception:
                pass
        if d == "sempre" and risco == "A" and ferramenta:
            self.agente.sempre.add(ferramenta)
        ok = d in ("sim", "sempre")
        self.emitir_bus("decisao", id=cid, ok=ok)
        return ok

    def _emitir(self, tipo, **d):
        if tipo == "ferramenta":
            self.atual["ferramenta"] = d.get("nome")
        self.emitir_bus(tipo, **d)

    # ---------- entrada ----------
    def tratar(self, upd: dict) -> None:
        if "callback_query" in upd:
            return self._botao(upd["callback_query"])
        msg = upd.get("message") or {}
        if not msg:
            return
        de = (msg.get("from") or {}).get("id")
        chat = (msg.get("chat") or {}).get("id")
        if not self.dono:
            # ainda sem dono: só informa o ID, não faz mais nada
            self.api.chamar("sendMessage", chat_id=chat, text=(
                f"Seu ID do Telegram é {de}.\nPara me liberar, coloque  dono_id = {de}  na seção [telegram] do config.toml e reinicie o Alfred."))
            return
        if de != self.dono or chat != self.dono:
            gate.registrar({"ferramenta": "telegram", "risco": "-", "acao": f"mensagem ignorada de {de}", "resultado": "estranho"})
            return
        texto = (msg.get("text") or "").strip()
        if texto in ("/start", "/ajuda"):
            self.enviar("Oi! Pode me escrever ou mandar áudio. /parar interrompe o que eu estiver fazendo. /tarefas mostra o checklist. /reiniciar reinicia o Alfred. /cota mostra quanto da cota do cérebro já foi usado hoje.")
            return
        if texto == "/reiniciar":
            return self.reiniciar()
        if texto == "/tarefas":
            from .tools.tarefas import checklist
            t = getattr(self.agente.ctx, "tarefas", None) if self.agente else None
            self.enviar(checklist(t) if t else "O checklist não está ligado.")
            return
        if texto == "/cota":
            from . import cota
            self.enviar(cota.resumo())
            return
        if texto == "/parar":
            gate.PARADO.set()
            for info in list(self.pendentes.values()):
                info["decisao"] = "nao"
                info["ev"].set()
            self.emitir_bus("parado")
            self.enviar("Parei.")
            return
        audio = msg.get("voice") or msg.get("audio")
        if audio:
            return self._disparar(self._trabalhar_audio, audio)
        if texto:
            return self._disparar(self._trabalhar, texto)
        self.enviar("Por enquanto eu entendo texto e áudio.")

    def _botao(self, cq: dict) -> None:
        de = (cq.get("from") or {}).get("id")
        try:
            self.api.chamar("answerCallbackQuery", callback_query_id=cq.get("id"))
        except Exception:
            pass
        if de != self.dono:
            return
        decisao, _, cid = str(cq.get("data", "")).partition(":")
        info = self.pendentes.get(cid)
        if not info:
            return
        info["decisao"] = decisao if decisao in ("sim", "sempre", "nao") else "nao"
        info["ev"].set()
        msg = cq.get("message") or {}
        if msg.get("message_id"):
            marca = {"sim": "Você disse: SIM", "sempre": "Você disse: SEMPRE", "nao": "Você disse: NÃO"}[info["decisao"]]
            try:
                self.api.chamar("editMessageText", chat_id=self.dono, message_id=msg["message_id"], text=f"{msg.get('text', '')}\n\n{marca}")
            except Exception:
                pass

    def _disparar(self, alvo, arg) -> None:
        if not self.ocupado.acquire(blocking=False):
            self.enviar("Estou terminando outra tarefa. Me mande de novo em instantes.")
            return
        if self.em_thread:
            threading.Thread(target=alvo, args=(arg,), daemon=True, name="telegram-pedido").start()
        else:
            alvo(arg)

    def _trabalhar_audio(self, audio: dict) -> None:
        texto = ""
        try:
            if not self.transcrever:
                self.enviar("Para entender áudio preciso da chave gratuita da Groq: python -m alfred chave groq")
            else:
                texto = self.transcrever(self.api.baixar(audio["file_id"]), "audio.ogg")
                self.enviar(f"Entendi: \"{texto}\"" if texto else "Não consegui entender o áudio.")
        except Exception as e:
            texto = ""
            try:
                self.enviar(f"Falhou ao ler o áudio: {e}")
            except Exception:
                pass
        if not texto:
            self.ocupado.release()
            return
        self._trabalhar(texto)        # _trabalhar libera a trava no fim

    def _trabalhar(self, texto: str) -> None:
        try:
            self.emitir_bus("usuario", texto=texto + "  (pelo Telegram)")
            try:
                self.api.chamar("sendChatAction", chat_id=self.dono, action="typing")
            except Exception:
                pass
            resp = self.agente.responder(texto[:4000], self._emitir, self.confirmar, origem="telegram")
            self.emitir_bus("resposta", texto=resp)
            self.enviar(resp)
        except Exception as e:
            self.emitir_bus("erro", texto=f"{type(e).__name__}: {e}")
            try:
                self.enviar(f"Deu erro: {type(e).__name__}: {e}")
            except Exception:
                pass
        finally:
            self.ocupado.release()

    # ---------- reinício ----------
    def reiniciar(self) -> None:
        import os
        from .config import DADOS
        from .servico import REINICIAR
        if os.environ.get("ALFRED_SERVICO") != "1":
            self.enviar("Estou aberto pelo iniciar.bat (janela preta), não pelo serviço: feche a janela e abra de novo.")
            return
        try:
            self.api.chamar("getUpdates", offset=self.offset, timeout=0)     # confirma o /reiniciar, senão ele volta em loop
        except Exception:
            pass
        (DADOS / "reiniciado.flag").write_text("telegram", encoding="utf-8")
        gate.registrar({"ferramenta": "telegram", "risco": "-", "acao": "reiniciar o Alfred (pedido pelo Telegram)", "resultado": "ok"})
        self.enviar("Reiniciando… volto em uns 10 segundos.")
        threading.Timer(1.0, lambda: self.sair(REINICIAR)).start()

    @staticmethod
    def sair(codigo: int) -> None:
        import os
        os._exit(codigo)

    # ---------- laço ----------
    def receber_uma_vez(self, espera: int = 25) -> int:
        atualizacoes = self.api.chamar("getUpdates", offset=self.offset, timeout=espera, allowed_updates=["message", "callback_query"])
        for upd in atualizacoes:
            self.offset = max(self.offset, upd["update_id"] + 1)
            try:
                self.tratar(upd)
            except Exception as e:
                self.emitir_bus("erro", texto=f"Telegram: {e}")
        return len(atualizacoes)

    def apresentar(self) -> str:
        """Confere o token com getMe e descreve o estado (vai para a janela preta e para a tela). Nunca mostra o token."""
        try:
            eu = self.api.chamar("getMe")
            webhook = self.api.chamar("getWebhookInfo").get("url")
        except Exception as e:
            return f"Telegram: NÃO conectou ({e}). Se for 'Unauthorized', o token está errado: copie de novo no @BotFather e rode  python -m alfred chave telegram --colar"
        if webhook:
            self.api.chamar("deleteWebhook")
        dono = f"só atende o ID {self.dono}" if self.dono else "ainda sem dono: mande 'oi' ao bot e ele responde com o seu ID"
        return f"Telegram: ligado como @{eu.get('username', '?')} ({dono})"

    def iniciar(self, parar: threading.Event) -> threading.Thread:
        def laco():
            estado = self.apresentar()
            print(estado, flush=True)
            self.emitir_bus("info" if "ligado" in estado else "erro", texto=estado)
            from .config import DADOS
            flag = DADOS / "reiniciado.flag"
            if flag.exists():
                flag.unlink(missing_ok=True)
                try:
                    self.enviar("Voltei. Alfred reiniciado e funcionando.")
                except Exception:
                    pass
            pausa, ultimo_erro = 2, ""
            while not parar.is_set():
                try:
                    self.receber_uma_vez()
                    if ultimo_erro:
                        print("Telegram: conexão de volta.", flush=True)
                    pausa, ultimo_erro = 2, ""
                except Exception as e:      # sem internet, Telegram fora: espera e tenta de novo
                    msg = f"Telegram sem conexão ({e}); tento de novo em {pausa}s"
                    if str(e) != ultimo_erro:      # na janela preta, só quando o erro muda (não vira sirene)
                        print(msg, flush=True)
                    ultimo_erro = str(e)
                    self.emitir_bus("erro", texto=msg)
                    parar.wait(pausa)
                    pausa = min(pausa * 2, 120)
        t = threading.Thread(target=laco, daemon=True, name="telegram")
        t.start()
        return t


def montar(agente, ocupado, emitir_bus) -> CanalTelegram | None:
    """Cria o canal se [telegram] ativo = true e o token estiver no cofre. Senão, None."""
    from . import segredos
    cfg = agente.ctx.cfg.get("telegram", {})
    if not cfg.get("ativo"):
        print("Telegram: desligado (config.toml, [telegram] ativo = false)", flush=True)
        return None
    token = segredos.obter("telegram")
    if not token:
        msg = "Telegram ativo mas sem token no cofre: rode  python -m alfred chave telegram --colar"
        print(msg, flush=True)
        emitir_bus("erro", texto=msg)
        return None
    groq = segredos.obter("groq")
    return CanalTelegram(ApiTelegram(token), cfg.get("dono_id") or None, agente, ocupado, emitir_bus,
                         transcrever_groq(groq) if groq else None)
