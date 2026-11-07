"""Servidor MCP de mentira (stdio) usado nos testes."""
import json
import sys

for linha in sys.stdin:
    m = json.loads(linha)
    i, met = m.get("id"), m.get("method")
    if met == "initialize":
        r = {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}, "serverInfo": {"name": "falso", "version": "0"}}
    elif met == "tools/list":
        r = {"tools": [{"name": "somar", "description": "soma dois números", "inputSchema": {"type": "object", "properties": {"a": {"type": "number"}, "b": {"type": "number"}}, "required": ["a", "b"]}},
                       {"name": "falhar", "description": "sempre falha", "inputSchema": {"type": "object", "properties": {}}}]}
    elif met == "tools/call":
        n, a = m["params"]["name"], m["params"]["arguments"]
        r = {"content": [{"type": "text", "text": str(a["a"] + a["b"])}]} if n == "somar" else {"isError": True, "content": [{"type": "text", "text": "deu ruim"}]}
    else:
        continue
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": i, "result": r}) + "\n")
    sys.stdout.flush()
