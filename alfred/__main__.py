"""python -m alfred            -> abre o Alfred
python -m alfred chave NOME   -> guarda uma chave no cofre do sistema
python -m alfred testar       -> confere se está tudo pronto
python -m alfred oi           -> uma chamada real ao cérebro ("diga oi"), com tokens e custo
python -m alfred mcp          -> Alfred como servidor MCP (Claude Desktop/Code pedem coisas a ele)
python -m alfred ponte        -> liga a ponte do WhatsApp (o Alfred lê e prepara respostas)
python -m alfred atendente    -> liga o atendente automático de clientes no WhatsApp"""
import sys
import threading
import webbrowser


def _whatsapp(modo: str) -> int:
    """Roda canais/whatsapp/whatsapp.js com a chave tirada do cofre (nunca de arquivo)."""
    import os
    import shutil
    import subprocess
    from . import segredos
    from .config import BASE
    node = shutil.which("node")
    if not node:
        print("Precisa do Node.js 22.13 ou mais novo (recomendado: 24 LTS). Instale e rode de novo.")
        return 1
    pasta = BASE / "canais" / "whatsapp"
    if not (pasta / "node_modules").exists():
        print(f"Primeiro rode:  cd {pasta}  &&  npm install")
        return 1
    env = {**os.environ, "MODO": modo}
    chave = segredos.obter("groq")
    if chave:
        env["ALFRED_CHAVE_GROQ"] = chave
    return subprocess.call([node, "whatsapp.js"], cwd=pasta, env=env)


def _diagnostico(cfg: dict) -> None:
    """Quando o 'oi' falha: confere o formato da chave (sem mostrá-la) e se o provedor aceita a chave e o modelo."""
    import httpx
    from . import cerebro, segredos
    prov = cerebro.PROVEDORES[cfg["provedor"]]
    chave = segredos.obter(prov["chave"]) or ""
    estranhos = [c for c in chave if not c.isprintable() or c.isspace()]
    prefixo = {"groq": "gsk_", "anthropic": "sk-ant-"}.get(cfg["provedor"], "")
    print("\n-- diagnóstico (a chave não é mostrada) --")
    print(f"chave no cofre: {len(chave)} caracteres" + (f"; começa com '{prefixo}': {'sim' if chave.startswith(prefixo) else 'NÃO'}" if prefixo else ""))
    if estranhos:
        print(f"[FALTA] a chave tem {len(estranhos)} caractere(s) invisível(is) ou espaço (comum ao colar com Ctrl+V no PowerShell antigo)."
              f"  -> guarde de novo: python -m alfred chave {prov['chave']}  e cole com o botão direito do mouse")
    if prov["tipo"] != "openai":
        return
    try:
        r = httpx.get(f"{prov['base']}/models", headers={"authorization": f"Bearer {chave.strip()}"}, timeout=20)
    except httpx.HTTPError as e:
        print(f"[FALTA] sem conexão com {prov['base']}: {type(e).__name__}: {e}")
        return
    print(f"lista de modelos: HTTP {r.status_code}  (servidor: {r.headers.get('server', '?')}, tipo: {r.headers.get('content-type', '?')}, {len(r.content)} bytes)")
    if r.status_code == 200:
        ids = sorted(m.get("id", "") for m in r.json().get("data", []))
        modelo = cfg.get("modelo") or prov["modelo"]
        print(f"modelo '{modelo}' disponível: {'sim' if modelo in ids else 'NÃO'}")
        print("modelos da conta: " + ", ".join(ids)[:900])
    else:
        print("resposta: " + (r.text[:300] or "(vazia)"))


def oi() -> int:
    """Portão da Fase 0: uma chamada real ao cérebro. Mostra a resposta, os tokens e o custo; nunca a chave."""
    from . import cerebro
    from .config import carregar
    cfg = carregar()
    try:
        p = cerebro.Provedor(cfg["provedor"], cfg.get("modelo", ""))
        r = p.completar("Você é um assistente. Responda em português do Brasil, em uma frase curta.",
                        [{"role": "user", "content": "Diga oi."}], [])
    except cerebro.ErroCerebro as e:
        msg = str(e)
        if msg.startswith("401"):
            msg += "  -> chave inválida ou revogada: crie outra no painel do provedor e rode: python -m alfred chave " + cfg["provedor"]
        elif msg.startswith("400") and "credit" in msg.lower():
            msg += "  -> sem crédito na conta: adicione crédito no painel do provedor"
        print(f"[FALTA] o cérebro não respondeu: {msg}")
        _diagnostico(cfg)
        return 1
    print(f"[ok]   {cfg['provedor']} / {p.modelo} respondeu: {r.texto}")
    print(f"[ok]   {r.entrada} tokens de entrada, {r.saida} de saída, custo estimado US$ {p.custo(r):.6f}")
    return 0


def main(argv: list[str]) -> int:
    if argv and argv[0] == "chave":
        from .segredos import cli
        return cli(argv[1:])
    if argv and argv[0] == "mcp":
        from .mcp_servidor import rodar
        return rodar()
    if argv and argv[0] in ("ponte", "atendente"):
        return _whatsapp("atendente" if argv[0] == "atendente" else "ponte")
    if argv and argv[0] == "oi":
        return oi()
    if argv and argv[0] == "servico":
        from .servico import rodar
        return rodar()
    if argv and argv[0] == "testar":
        from .autoteste import rodar
        return rodar()
    from .config import carregar
    from .servico import porta_ocupada
    porta = int(carregar()["porta"])
    if porta_ocupada(porta):
        # já tem um Alfred aberto (o serviço escondido, por exemplo): não abre outro, só mostra a tela
        print(f"O Alfred já está aberto. Tela: http://127.0.0.1:{porta}/")
        if "--sem-navegador" not in argv:
            webbrowser.open(f"http://127.0.0.1:{porta}/")
        return 0
    import uvicorn
    from .servidor import criar_app
    app = criar_app()
    if "--sem-navegador" not in argv:
        threading.Timer(1.2, lambda: webbrowser.open(f"http://127.0.0.1:{porta}/")).start()
    print(f"Alfred no ar em http://127.0.0.1:{porta}/  (Ctrl+C para parar)")
    uvicorn.run(app, host="127.0.0.1", port=porta, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
