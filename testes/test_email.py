"""E-mail: texto de verdade (multipart/HTML), não marca como lido, rascunho na pasta certa, envio desligado por padrão."""
from email.message import EmailMessage

import pytest

from alfred.gate import Risco
from alfred.tools import email as email_ferr
from test_tudo import ctx  # noqa: F401  (fixture)


def _msg_html():
    m = EmailMessage()
    m["From"], m["Subject"], m["Date"] = "=?utf-8?q?Jo=C3=A3o?= <joao@x.com>", "Pedido atacado", "Tue, 03 Nov 2026 12:00:00 -0300"
    m.set_content("versão texto: quero 50 potes de whey")
    m.add_alternative("<html><body><p>quero <b>50</b> potes</p></body></html>", subtype="html")
    m.add_attachment(b"%PDF-1.4 lixo binario", maintype="application", subtype="pdf", filename="tabela.pdf")
    return m.as_bytes()


class ImapFalso:
    def __init__(self, *a):
        self.vistos, self.anexados, self.readonly = [], [], None

    def login(self, u, s):
        self.senha = s

    def select(self, pasta, readonly=False):
        self.readonly = readonly
        return "OK", [b"2"]

    def search(self, *a):
        return "OK", [b"1 2"]

    def fetch(self, i, oque):
        self.vistos.append(oque)
        if "SIZE" in oque:
            return "OK", [b"1 (RFC822.SIZE 3000000)" if i == b"1" else b"2 (RFC822.SIZE 900)"]
        return "OK", [(b"x", _msg_html()), b")"]

    def list(self):
        return "OK", [b'(\\HasNoChildren) "/" "INBOX"', b'(\\HasNoChildren \\Drafts) "/" "[Gmail]/Rascunhos"']

    def append(self, pasta, flags, data, corpo):
        self.anexados.append((pasta, flags, corpo))
        return "OK", [b"APPEND completed"]

    def logout(self):
        pass


@pytest.fixture()
def fs(ctx, monkeypatch):
    ctx.cfg["email"] = {"ativo": True, "imap": "imap.gmail.com", "smtp": "smtp.gmail.com", "usuario": "eu@gmail.com", "permitir_envio": False}
    falso = ImapFalso()
    monkeypatch.setattr(email_ferr.imaplib, "IMAP4_SSL", lambda *a: falso)
    monkeypatch.setattr(email_ferr.segredos, "obter", lambda n: "abcd efgh ijkl mnop")
    return {f.nome: f for f in email_ferr.criar(ctx)}, falso


def test_listar_texto_limpo_sem_marcar_lido(fs):
    f, imap = fs
    saida = f["email_listar"].executar(quantidade=5)
    assert imap.readonly is True and imap.senha == "abcdefghijklmnop"
    assert "De: João <joao@x.com>" in saida and "quero 50 potes de whey" in saida and "%PDF" not in saida and "03/11" in saida
    assert "(BODY.PEEK[HEADER])" in imap.vistos and "(BODY.PEEK[])" in imap.vistos     # o grande (3 MB) só pelo cabeçalho
    assert "2 não lidos" in saida


def test_so_html_vira_texto():
    m = EmailMessage()
    m["From"], m["Subject"] = "a@b", "x"
    m.set_content("<html><head><style>p{}</style></head><body><p>Olá &amp; tchau</p></body></html>", subtype="html")
    assert "Olá & tchau" in email_ferr._resumo_msg(m.as_bytes()) and "style" not in email_ferr._resumo_msg(m.as_bytes())


def test_rascunho_na_pasta_rascunhos_e_amarelo(fs):
    f, imap = fs
    assert f["email_rascunho"].risco is Risco.AMARELO
    r = f["email_rascunho"].executar(para="cliente@x.com", assunto="Orçamento", corpo="Segue")
    assert imap.anexados[0][0] == '"[Gmail]/Rascunhos"' and "Rascunhos" in r and "envie você" in r


def test_envio_desligado_por_padrao(fs, ctx):
    f, _ = fs
    assert "email_enviar" not in f
    ctx.cfg["email"]["permitir_envio"] = True
    liga = {x.nome: x for x in email_ferr.criar(ctx)}
    assert liga["email_enviar"].risco is Risco.VERMELHO


def test_varias_contas_todas_pular_e_uma_com_erro(ctx, monkeypatch):
    ctx.cfg["email"] = {"ativo": True, "permitir_envio": False, "contas": [
        {"nome": "pessoal", "usuario": "eu@gmail.com", "imap": "imap.gmail.com"},
        {"nome": "contato", "usuario": "contato@loja.com.br", "imap": "imap.hostinger.com", "smtp": "smtp.hostinger.com"}]}
    senhas = {"email-pessoal": "abcd efgh ijkl mnop", "email-contato": "senha com espaco"}
    logins = []

    class Imap(ImapFalso):
        def __init__(self, host):
            super().__init__()
            self.host = host

        def login(self, u, s):
            logins.append((self.host, u, s))
            if self.host == "imap.hostinger.com" and u == "falha":
                raise email_ferr.imaplib.IMAP4.error("auth")
    monkeypatch.setattr(email_ferr.imaplib, "IMAP4_SSL", Imap)
    monkeypatch.setattr(email_ferr.segredos, "obter", lambda n: senhas.get(n))
    fs = {f.nome: f for f in email_ferr.criar(ctx)}
    saida = fs["email_listar"].executar()
    assert "== pessoal (eu@gmail.com)" in saida and "== contato (contato@loja.com.br)" in saida
    assert ("imap.gmail.com", "eu@gmail.com", "abcdefghijklmnop") in logins                  # Gmail: tira os espaços
    assert ("imap.hostinger.com", "contato@loja.com.br", "senha com espaco") in logins      # Hostinger: senha como está
    s2 = fs["email_listar"].executar(conta="contato", quantidade=1)
    assert "do 1º ao 1º" in s2 and "pular=1" in s2
    assert "do 2º ao 2º" in fs["email_listar"].executar(conta="contato", quantidade=1, pular=1)
    senhas.pop("email-contato")
    s3 = fs["email_listar"].executar()
    assert "== pessoal" in s3 and "contato: não consegui ler" in s3 and "chave email-contato --colar" in s3
    with pytest.raises(ValueError, match="diga qual conta"):
        fs["email_rascunho"].executar(para="a@b", assunto="x", corpo="y")
    with pytest.raises(ValueError, match="não existe"):
        fs["email_listar"].executar(conta="outra")


def test_cofre_aceita_senha_de_app_com_espacos(monkeypatch, capsys):
    from alfred import segredos
    guardado = {}
    monkeypatch.setattr(segredos, "guardar", lambda n, v: guardado.update({n: v}))
    monkeypatch.setattr(segredos, "_area_de_transferencia", lambda: "abcd efgh ijkl mnop")
    monkeypatch.setattr(segredos, "_limpar_area_de_transferencia", lambda: None)
    assert segredos.cli(["email-pessoal", "--colar"]) == 0 and guardado["email-pessoal"] == "abcd efgh ijkl mnop"
    monkeypatch.setattr(segredos.getpass, "getpass", lambda msg: "\x16")
    assert segredos.cli(["email-pessoal"]) == 1


def test_leitura_de_email_e_agenda_sempre_ligadas():
    from alfred.tools import grupo_de
    assert grupo_de("email_listar") == "nucleo" and grupo_de("agenda_hoje") == "nucleo"
    assert grupo_de("email_rascunho") == "comunicacao"        # escrever continua no grupo, pedindo confirmação
