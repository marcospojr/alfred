"""Agenda e e-mails em texto para o Escritório (C:/escritorio-ia) mandar como aviso no celular, sem passar pelo modelo nem pelo Telegram.

Uso: .venv/Scripts/python.exe -m alfred.dia_cli agenda [dias]   (padrão 1 = hoje; 2 = hoje e amanhã)
     .venv/Scripts/python.exe -m alfred.dia_cli emails          (quantos não lidos por conta)
Só lê (ferramentas verdes). Os endereços iCal e as senhas de e-mail continuam no cofre do Alfred.
"""
import re
import sys
from types import SimpleNamespace

from .config import carregar
from .tools import agenda, email


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ctx = SimpleNamespace(cfg=carregar())
    modo = argv[0] if argv else "agenda"
    if modo == "agenda":
        dias = int(argv[1]) if len(argv) > 1 and argv[1].isdigit() else 1
        ferr = {f.nome: f for f in agenda.criar(ctx)}
        print(ferr["agenda_hoje"].executar(dias=dias))
    elif modo == "emails":
        ferr = {f.nome: f for f in email.criar(ctx)}
        if "email_listar" not in ferr:
            print("e-mail não configurado")
            return 0
        # só a contagem: assunto e remetente são de terceiros e não vão para o aviso
        saida = str(ferr["email_listar"].executar(conta="todas", quantidade=1, so_nao_lidos=True))
        print("\n".join(l for l in saida.splitlines() if re.search(r"n[ãa]o lid|conta|^\S+@", l, re.I)) or saida.splitlines()[0])
    else:
        print("uso: agenda [dias] | emails")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
