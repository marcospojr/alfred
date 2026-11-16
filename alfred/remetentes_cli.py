"""Raio-x dos não lidos de uma conta Gmail: quantos por categoria e por remetente. Só lê (INBOX em readonly, nada vira lido).

Uso: .venv/Scripts/python.exe -m alfred.remetentes_cli <conta> [quantos remetentes, padrão 25]
"""
import imaplib
import re
import sys
from collections import Counter
from email.utils import parseaddr

from . import segredos
from .config import carregar
from .tools.email import _dec, contas_de


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    if not argv:
        print("uso: remetentes_cli <conta> [n]")
        return 2
    top = int(argv[1]) if len(argv) > 1 and argv[1].isdigit() else 25
    c = next((x for x in contas_de(carregar()["email"]) if argv[0].lower() in (x["nome"].lower(), x["usuario"].lower())), None)
    if not c:
        print("conta não encontrada")
        return 2
    m = imaplib.IMAP4_SSL(c["imap"])
    m.login(c["usuario"], (segredos.obter(c["chave"]) or "").replace(" ", ""))
    m.select("INBOX", readonly=True)
    total = len(m.search(None, "UNSEEN")[1][0].split())
    print(f"{c['usuario']}: {total} não lidos na caixa de entrada")
    if "gmail" in c["imap"]:
        for cat in ["primary", "promotions", "social", "updates", "forums"]:
            n = len(m.search(None, "X-GM-RAW", f'"is:unread category:{cat}"')[1][0].split())
            print(f"  categoria {cat}: {n}")
        antigos = len(m.search(None, "X-GM-RAW", '"is:unread older_than:30d"')[1][0].split())
        print(f"  mais velhos que 30 dias: {antigos}")
    ids = m.search(None, "UNSEEN")[1][0].split()
    remet = Counter()
    for i in range(0, len(ids), 200):
        _, dados = m.fetch(b",".join(ids[i:i + 200]), "(BODY.PEEK[HEADER.FIELDS (FROM)])")
        for parte in dados:
            if isinstance(parte, tuple):
                nome, end = parseaddr(_dec(re.sub(r"^From:\s*", "", parte[1].decode("utf-8", "replace").strip(), flags=re.I)))
                remet[end.lower() or nome] += 1
    print(f"\nRemetentes com mais não lidos (top {top}):")
    for end, n in remet.most_common(top):
        print(f"  {n:5d}  {end}")
    m.logout()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
