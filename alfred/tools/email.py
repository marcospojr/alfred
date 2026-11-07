"""E-mail por IMAP/SMTP (Gmail, Outlook...). Use 'senha de app'; ela fica no cofre (python -m alfred chave email --colar).

- email_listar (verde): lê a caixa de entrada sem marcar como lido; extrai o texto de verdade (sem código de e-mail).
- email_rascunho (amarelo): salva um rascunho na pasta Rascunhos; quem envia é você, pelo Gmail.
- email_enviar (vermelho): só existe se [email] permitir_envio = true no config.toml. Sempre confirma com os valores.
"""
import email
import imaplib
import re
import smtplib
import time
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import parsedate_to_datetime
from html import unescape

from .. import segredos
from ..gate import Risco
from . import Ferramenta, esquema, inteiro, texto

TAMANHO_MAX = 2_000_000       # e-mail maior que isso (anexos): lê só o cabeçalho
TRECHO = 300                  # caracteres de cada e-mail que vão para o cérebro (cota da Groq é por minuto)


def _dec(v: str | None) -> str:
    try:
        return str(make_header(decode_header(v or ""))) if v else ""
    except Exception:
        return v or ""


def _texto_de(msg) -> str:
    """Primeira parte text/plain; se só houver HTML, tira as tags. Ignora anexos."""
    html = ""
    partes = msg.walk() if msg.is_multipart() else [msg]
    for p in partes:
        if p.get_content_maintype() == "multipart" or p.get_filename() or "attachment" in str(p.get("Content-Disposition", "")):
            continue
        try:
            corpo = p.get_payload(decode=True) or b""
            txt = corpo.decode(p.get_content_charset() or "utf-8", "replace")
        except (LookupError, AttributeError):
            continue
        if p.get_content_type() == "text/plain" and txt.strip():
            return txt
        if p.get_content_type() == "text/html" and not html:
            html = txt
    html = re.sub(r"(?is)<(script|style|head).*?</\1>", " ", html)
    return unescape(re.sub(r"<[^>]+>", " ", html))


def _resumo_msg(cru: bytes) -> str:
    msg = email.message_from_bytes(cru)
    try:
        quando = parsedate_to_datetime(msg["Date"]).astimezone().strftime("%d/%m %H:%M")
    except Exception:
        quando = msg["Date"] or "?"
    trecho = " ".join(_texto_de(msg).split())[:TRECHO]
    return f"De: {_dec(msg['From'])}\nAssunto: {_dec(msg['Subject'])}\nData: {quando}\n{trecho}\n"


def _pasta_rascunhos(m) -> str:
    """Acha a pasta de rascunhos pelo marcador \\Drafts (o nome muda com o idioma: [Gmail]/Rascunhos, [Gmail]/Drafts...)."""
    _, linhas = m.list()
    for ln in linhas or []:
        s = ln.decode("utf-8", "replace") if isinstance(ln, bytes) else str(ln)
        if "\\Drafts" in s:
            nome = s.rsplit(' "/" ', 1)[-1].strip()
            return nome
    return "Drafts"


def contas_de(cfg: dict) -> list[dict]:
    """[[email.contas]] no config.toml; sem isso, a conta única antiga (usuario/imap/smtp)."""
    contas = []
    for c in cfg.get("contas") or []:
        if c.get("usuario"):
            contas.append({"nome": c.get("nome") or c["usuario"].split("@")[0], "usuario": c["usuario"],
                           "imap": c.get("imap", "imap.gmail.com"), "smtp": c.get("smtp", "smtp.gmail.com"), "chave": f"email-{c.get('nome') or c['usuario'].split('@')[0]}"})
    if not contas and cfg.get("usuario"):
        contas.append({"nome": cfg["usuario"].split("@")[0], "usuario": cfg["usuario"], "imap": cfg.get("imap", "imap.gmail.com"),
                       "smtp": cfg.get("smtp", "smtp.gmail.com"), "chave": "email"})
    return contas


def criar(ctx):
    cfg = ctx.cfg["email"]
    if not cfg.get("ativo"):
        return []
    contas = contas_de(cfg)
    if not contas:
        return []
    nomes = [c["nome"] for c in contas]

    def _conta(nome: str | None) -> dict:
        if not nome:
            if len(contas) == 1:
                return contas[0]
            raise ValueError(f"diga qual conta: {', '.join(nomes)}")
        for c in contas:
            if nome.lower() in (c["nome"].lower(), c["usuario"].lower()):
                return c
        raise ValueError(f"conta '{nome}' não existe; as contas são: {', '.join(nomes)}")

    def _senha(c: dict) -> str:
        s = segredos.obter(c["chave"])
        if not s:
            raise RuntimeError(f"sem senha da conta {c['nome']}. Rode: python -m alfred chave {c['chave']} --colar")
        return s.replace(" ", "") if "gmail" in c["imap"] else s      # Gmail mostra a senha de app em 4 blocos com espaço

    def _imap(c: dict):
        m = imaplib.IMAP4_SSL(c["imap"])
        try:
            m.login(c["usuario"], _senha(c))
        except imaplib.IMAP4.error as e:
            dica = "use uma SENHA DE APP (myaccount.google.com/apppasswords), não a senha normal" if "gmail" in c["imap"] else "confira a senha da caixa de e-mail"
            raise RuntimeError(f"a conta {c['nome']} recusou o login ({e}): {dica}")
        return m

    def _listar_uma(c: dict, quantidade: int, so_nao_lidos: bool, pular: int) -> str:
        m = _imap(c)
        try:
            m.select("INBOX", readonly=True)          # readonly: nada é marcado como lido
            _, ids = m.search(None, "UNSEEN" if so_nao_lidos else "ALL")
            lista = ids[0].split()[::-1]               # mais novos primeiro
            fatia = lista[pular:pular + quantidade]
            saida = []
            for i in fatia:
                _, tam = m.fetch(i, "(RFC822.SIZE)")
                n = re.search(rb"RFC822\.SIZE (\d+)", tam[0] if tam and isinstance(tam[0], bytes) else b"")
                parte = "BODY.PEEK[HEADER]" if n and int(n.group(1)) > TAMANHO_MAX else "BODY.PEEK[]"
                _, d = m.fetch(i, f"({parte})")
                cru = next((x[1] for x in d if isinstance(x, tuple)), b"")
                saida.append(_resumo_msg(cru))
            tipo = "não lidos" if so_nao_lidos else "na caixa"
            cab = f"== {c['nome']} ({c['usuario']}): {len(lista)} {tipo}"
            if not saida:
                return cab + (" ==" if not lista else f"; nada a partir do {pular + 1}º ==")
            cab += f"; mostrando do {pular + 1}º ao {pular + len(saida)}º"
            if pular + len(saida) < len(lista):
                cab += f" (para ver mais: pular={pular + len(saida)})"
            return cab + " ==\n\n" + "\n".join(saida)
        finally:
            try:
                m.logout()
            except Exception:
                pass

    def listar(conta: str = "todas", quantidade: int = 10, so_nao_lidos: bool = True, pular: int = 0):
        quantidade, pular = max(1, min(quantidade, 25)), max(0, pular)
        alvo = contas if (conta or "todas").lower() == "todas" else [_conta(conta)]
        if len(alvo) > 1:
            quantidade = min(quantidade, 5)            # várias contas de uma vez: 5 de cada, para caber na cota por minuto
        partes = []
        for c in alvo:
            try:
                partes.append(_listar_uma(c, quantidade, so_nao_lidos, pular))
            except Exception as e:                     # uma conta com problema não esconde as outras
                partes.append(f"== {c['nome']}: não consegui ler ({e}) ==")
        return "\n\n".join(partes)

    def rascunho(para: str, assunto: str, corpo: str, conta: str = ""):
        c = _conta(conta)
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = c["usuario"], para, assunto
        msg.set_content(corpo)
        m = _imap(c)
        try:
            pasta = _pasta_rascunhos(m)
            r = m.append(pasta, "(\\Draft)", imaplib.Time2Internaldate(time.time()), msg.as_bytes())
            if r[0] != "OK":
                raise RuntimeError(f"o servidor não aceitou o rascunho: {r}")
        finally:
            try:
                m.logout()
            except Exception:
                pass
        return f"rascunho salvo em {pasta} da conta {c['nome']} (para {para}, assunto '{assunto}'). Abra o e-mail, revise e envie você."

    def enviar(para: str, assunto: str, corpo: str, conta: str = ""):
        c = _conta(conta)
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = c["usuario"], para, assunto
        msg.set_content(corpo)
        with smtplib.SMTP_SSL(c["smtp"], 465) as s:
            s.login(c["usuario"], _senha(c))
            s.send_message(msg)
        return f"e-mail enviado por {c['usuario']} para {para}"

    desc_conta = texto(f"conta: {', '.join(nomes)}" + (" ou 'todas'" if len(nomes) > 1 else ""))
    ferr = [
        Ferramenta("email_listar", "Lista e-mails da caixa de entrada (só leitura; não marca como lido). Use para resumir. Para ver os próximos, use 'pular'.",
                   esquema({"conta": desc_conta, "quantidade": inteiro("1 a 25 (padrão 10; com 'todas', 5 de cada)"), "so_nao_lidos": {"type": "boolean"},
                            "pular": inteiro("quantos pular (para ver os próximos)")}), Risco.VERDE, listar,
                   lambda conta="todas", quantidade=10, so_nao_lidos=True, pular=0: f"ler e-mails ({conta}, {quantidade} {'não lidos' if so_nao_lidos else 'mais recentes'}" + (f", a partir do {pular + 1}º" if pular else "") + ")", externo=True),
        Ferramenta("email_rascunho", "Salva um RASCUNHO de e-mail na pasta Rascunhos da conta. Não envia: a pessoa revisa e envia.",
                   esquema({"para": texto("destinatário"), "assunto": texto("assunto"), "corpo": texto("texto"), "conta": desc_conta}, ["para", "assunto", "corpo"]), Risco.AMARELO,
                   rascunho, lambda para, assunto, corpo, conta="": f"salvar RASCUNHO{' na conta ' + conta if conta else ''} para {para}. Assunto: {assunto}. Texto: {corpo[:300]}"),
    ]
    if cfg.get("permitir_envio"):
        ferr.append(Ferramenta("email_enviar", "Envia um e-mail em nome da pessoa.", esquema({"para": texto("destinatário"), "assunto": texto("assunto"), "corpo": texto("texto"), "conta": desc_conta}, ["para", "assunto", "corpo"]), Risco.VERMELHO,
                               enviar, lambda para, assunto, corpo, conta="": f"ENVIAR E-MAIL{' pela conta ' + conta if conta else ''} para {para}. Assunto: {assunto}. Texto: {corpo[:300]}"))
    return ferr
