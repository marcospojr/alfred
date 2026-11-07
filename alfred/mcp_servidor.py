"""O Alfred como servidor MCP (stdio): Claude Desktop, Claude Code ou qualquer cliente MCP passa a PEDIR coisas ao Alfred.
O pedido roda no Alfred (com o portão dele); ações que pedem confirmação aparecem na TELA do Alfred, para você aprovar.
Pré-requisito: o Alfred precisa estar aberto (python -m alfred). Configuração no cliente: veja docs/CLAUDE-E-ALFRED.md."""
import json
import sys

import httpx

from .config import DADOS, carregar

FERRAMENTAS = [
    {"name": "alfred_pedir", "description": "Pede algo ao Alfred, o operador do computador do usuário (arquivos, apps, agenda, e-mail, WhatsApp, automações, apps, APIs). Ações arriscadas esperam o 'sim' do usuário na tela do Alfred.",
     "inputSchema": {"type": "object", "properties": {"pedido": {"type": "string", "description": "o que o Alfred deve fazer, em português claro"}}, "required": ["pedido"]}},
    {"name": "alfred_estado", "description": "Mostra o estado do Alfred: cérebro, modo, gasto de hoje e ferramentas disponíveis.", "inputSchema": {"type": "object", "properties": {}}},
]


def _api(caminho: str, corpo: dict | None = None) -> dict:
    cfg = carregar()
    token = (DADOS / "api.token").read_text().strip()
    cab = {"x-alfred": token, "content-type": "application/json"}
    url = f"http://127.0.0.1:{cfg['porta']}{caminho}"
    r = httpx.post(url, headers=cab, json=corpo, timeout=190) if corpo is not None else httpx.get(url, headers=cab, timeout=20)
    r.raise_for_status()
    return r.json()


def tratar(m: dict) -> dict | None:
    metodo, i = m.get("method"), m.get("id")
    if metodo == "initialize":
        return {"jsonrpc": "2.0", "id": i, "result": {"protocolVersion": m["params"].get("protocolVersion", "2025-06-18"), "capabilities": {"tools": {}}, "serverInfo": {"name": "alfred", "version": "1.0.0"}}}
    if metodo == "tools/list":
        return {"jsonrpc": "2.0", "id": i, "result": {"tools": FERRAMENTAS}}
    if metodo == "tools/call":
        nome, args = m["params"]["name"], m["params"].get("arguments", {})
        try:
            if nome == "alfred_pedir":
                texto = _api("/api/pedir", {"texto": args.get("pedido", "")})["texto"]
            elif nome == "alfred_estado":
                e = _api("/api/estado")
                texto = f"{e['nome']} v{e['versao']} | cérebro {e['provedor']}/{e['modelo']} | modo {e['modo']} | gasto hoje US$ {e['gasto_hoje']}/{e['limite']} | ferramentas: " + ", ".join(f['nome'] for f in e['ferramentas'])
            else:
                return {"jsonrpc": "2.0", "id": i, "error": {"code": -32602, "message": f"ferramenta desconhecida: {nome}"}}
            return {"jsonrpc": "2.0", "id": i, "result": {"content": [{"type": "text", "text": texto}]}}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": i, "result": {"isError": True, "content": [{"type": "text", "text": f"Não consegui falar com o Alfred (ele está aberto? python -m alfred): {e}"}]}}
    if metodo == "ping":
        return {"jsonrpc": "2.0", "id": i, "result": {}}
    if i is not None:
        return {"jsonrpc": "2.0", "id": i, "error": {"code": -32601, "message": f"método não suportado: {metodo}"}}
    return None      # notificações


def rodar() -> int:
    for linha in sys.stdin:
        try:
            m = json.loads(linha)
        except json.JSONDecodeError:
            continue
        r = tratar(m)
        if r is not None:
            sys.stdout.write(json.dumps(r, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0
