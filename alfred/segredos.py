"""Chaves no cofre do sistema (Chaveiro no Mac, Gerenciador de Credenciais no Windows). Nunca em arquivo."""
import getpass
import re
import os
import sys

SERVICO = "alfred"


def obter(nome: str) -> str | None:
    """Variável de ambiente ALFRED_CHAVE_<NOME> tem prioridade (útil em servidor); depois o cofre."""
    env = os.environ.get(f"ALFRED_CHAVE_{nome.upper()}")
    if env:
        return env
    try:
        import keyring
        return keyring.get_password(SERVICO, nome)
    except Exception:
        return None


def guardar(nome: str, valor: str) -> None:
    import keyring
    keyring.set_password(SERVICO, nome, valor)


def remover(nome: str) -> None:
    import keyring
    try:
        keyring.delete_password(SERVICO, nome)
    except Exception:
        pass


PREFIXOS = {"groq": "gsk_", "anthropic": "sk-ant-", "agenda": "https://calendar.google.com/"}


def checar(nome: str, valor: str) -> str | None:
    """Devolve o motivo para NÃO guardar (sem mostrar a chave), ou None se parece ok."""
    if any(not c.isprintable() or c.isspace() for c in valor):
        return "a chave veio com caractere invisível ou espaço (o Ctrl+V nessa tela costuma gravar só o atalho)"
    if nome.startswith("agenda") and re.match(r"^(webcal|https)://p\d+-caldav\.icloud\.com/", valor):
        return None                       # agenda pública do iCloud (link de "Agenda Pública")
    if nome.startswith("agenda") and not valor.startswith("https://calendar.google.com/"):
        return "o endereço da agenda deve ser do Google (https://calendar.google.com/...) ou o link público do iCloud (webcal://p..-caldav.icloud.com/...)"
    if nome.startswith("agenda") and "/private-" not in valor:
        return "esse não é o endereço SECRETO: no Google Agenda use 'Endereço secreto no formato iCal' (tem 'private-' no meio)"
    if len(valor) < 16:
        return f"a chave veio com só {len(valor)} caractere(s); chaves de API são bem mais longas"
    pre = PREFIXOS.get(nome)
    if pre and not valor.startswith(pre):
        return f"chaves de '{nome}' começam com '{pre}'; confira se copiou a chave certa"
    return None


def _area_de_transferencia() -> str:
    import subprocess
    if sys.platform.startswith("win"):
        r = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"], capture_output=True, text=True, errors="replace")
    elif sys.platform == "darwin":
        r = subprocess.run(["pbpaste"], capture_output=True, text=True, errors="replace")
    else:
        r = subprocess.run(["xclip", "-selection", "clipboard", "-o"], capture_output=True, text=True, errors="replace")
    return (r.stdout or "").strip()


def _limpar_area_de_transferencia() -> None:
    import subprocess
    try:
        if sys.platform.startswith("win"):
            subprocess.run(["powershell", "-NoProfile", "-Command", "Set-Clipboard -Value ' '"], capture_output=True)
        elif sys.platform == "darwin":
            subprocess.run(["pbcopy"], input="", text=True)
    except Exception:
        pass


def cli(args: list[str]) -> int:
    """python -m alfred chave groq            -> pede a chave sem mostrar na tela e guarda no cofre.
    python -m alfred chave groq --colar    -> pega a chave que você copiou (área de transferência), guarda e limpa a área."""
    if not args:
        print("uso: python -m alfred chave <provedor|email|whatsapp|telegram|groq> [--colar]")
        return 2
    nome = args[0]
    colar = "--colar" in args[1:]
    if colar:
        valor = _area_de_transferencia().strip()
    else:
        valor = getpass.getpass(f"Cole a chave de '{nome}' (não aparece na tela) e aperte Enter: ").strip()
    if not valor:
        print("nada guardado." + ("" if colar else "  Dica: copie a chave e rode de novo com --colar"))
        return 1
    if nome == "email" or nome.startswith("email-"):
        # senha de e-mail: espaço é permitido (a senha de app do Gmail vem em 4 blocos); caractere invisível, não
        motivo = ("a senha veio com caractere invisível (o Ctrl+V nessa tela costuma gravar só o atalho)" if any(not c.isprintable() for c in valor)
                  else "a senha veio curta demais" if len(valor.replace(" ", "")) < 6 else None)
    else:
        motivo = checar(nome, valor) if nome in PREFIXOS or nome.startswith("agenda") or nome in ("openai", "gemini", "xai", "openrouter") else (
            "a chave veio com caractere invisível ou espaço" if any(not c.isprintable() or c.isspace() for c in valor) or len(valor) < 8 else None)
    if motivo:
        print(f"NÃO guardei: {motivo}.")
        print(f"  -> copie a chave de novo no site e rode:  python -m alfred chave {nome} --colar")
        return 1
    guardar(nome, valor)
    if colar:
        _limpar_area_de_transferencia()
    print(f"guardada no cofre do sistema ({len(valor)} caracteres)." + (" Limpei a área de transferência." if colar else ""))
    return 0


if __name__ == "__main__":
    sys.exit(cli(sys.argv[1:]))
