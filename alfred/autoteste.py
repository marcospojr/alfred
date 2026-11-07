"""Autoteste rápido para a pessoa (e para a IA) conferirem a instalação."""
import sys

from . import segredos
from .agente import Agente
from .config import carregar


def rodar() -> int:
    ok = True

    def linha(bom, msg):
        nonlocal ok
        ok = ok and bom
        print(("[ok]   " if bom else "[FALTA]"), msg)

    cfg = carregar()
    linha(sys.version_info >= (3, 11), f"Python {sys.version.split()[0]} (precisa 3.11+)")
    ag = Agente()
    linha(len(ag.registro.por_nome) > 8, f"{len(ag.registro.por_nome)} ferramentas carregadas: {', '.join(sorted(ag.registro.por_nome))[:200]}")
    chave = cfg["provedor"] == "ollama" or bool(segredos.obter(cfg["provedor"]))
    linha(chave, f"chave do provedor '{cfg['provedor']}' no cofre" + ("" if chave else f"  -> rode: python -m alfred chave {cfg['provedor']}"))
    try:
        ag.ctx.memoria.lembrar("autoteste", "ok")
        linha(bool(ag.ctx.memoria.fatos()), "memória (SQLite) funcionando")
        ag.ctx.memoria.esquecer("autoteste")
    except Exception as e:
        linha(False, f"memória: {e}")
    tg = cfg.get("telegram", {})
    if tg.get("ativo"):
        linha(bool(segredos.obter("telegram")), "token do bot do Telegram no cofre" + ("" if segredos.obter("telegram") else "  -> rode: python -m alfred chave telegram"))
        if segredos.obter("telegram"):
            from .telegram import ApiTelegram
            try:
                eu = ApiTelegram(segredos.obter("telegram")).chamar("getMe")
                linha(True, f"bot do Telegram responde: @{eu.get('username', '?')}")
            except Exception as e:
                linha(False, f"bot do Telegram não respondeu ({e})  -> token errado? copie no @BotFather e rode: python -m alfred chave telegram --colar")
        linha(bool(tg.get("dono_id")), "dono_id do Telegram no config.toml" + ("" if tg.get("dono_id") else "  -> mande uma mensagem ao bot: ele responde com o seu ID"))
        print("[ok]   áudio pelo Telegram (chave da Groq no cofre)" if segredos.obter("groq") else "[info]  sem chave da Groq: o Telegram entende só texto  -> python -m alfred chave groq")
    if cfg.get("email", {}).get("ativo"):
        import imaplib
        from .tools.email import contas_de
        for c in contas_de(cfg["email"]):
            senha = segredos.obter(c["chave"])
            if not senha:
                linha(False, f"e-mail {c['nome']}: sem senha no cofre  -> rode: python -m alfred chave {c['chave']} --colar")
                continue
            try:
                m = imaplib.IMAP4_SSL(c["imap"])
                m.login(c["usuario"], senha.replace(" ", "") if "gmail" in c["imap"] else senha)
                m.logout()
                linha(True, f"e-mail {c['nome']} ({c['usuario']}): login ok")
            except Exception as e:
                linha(False, f"e-mail {c['nome']} ({c['usuario']}): login falhou ({e})")
    for pasta in cfg["pastas"]:
        linha(True, f"pasta permitida: {pasta}")
    for mod in ("pyautogui", "playwright"):
        try:
            __import__(mod)
            linha(True, f"opcional '{mod}' instalado")
        except ImportError:
            print(f"[info]  opcional '{mod}' não instalado (controle de tela/navegador desligado)")
    print("\nTudo certo." if ok else "\nTem itens faltando acima.")
    return 0 if ok else 1
