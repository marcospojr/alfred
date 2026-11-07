"""Ferramentas para o Alfred enxergar e adicionar servidores MCP."""
import json

from ..gate import Risco
from ..mcp_cliente import ErroMcp, GerenteMcp
from . import Ferramenta, esquema, texto


def criar(ctx):
    def g() -> GerenteMcp:
        if ctx.mcp is None:
            ctx.mcp = GerenteMcp(ctx)
        return ctx.mcp

    def listar():
        cfg, ger = g().config(), g()
        linhas = [f"{c['nome']}: {c['comando']} {' '.join(c['args'])} | {'conectado' if c['nome'] in ger.clientes else 'erro: ' + ger.erros.get(c['nome'], 'não iniciou')}" for c in cfg]
        ferr = [n for n in ctx.agente.registro.por_nome if n.startswith("mcp_")]
        return ("\n".join(linhas) or "nenhum servidor MCP configurado") + (f"\nferramentas MCP ativas: {len(ferr)}" if ferr else "")

    def adicionar(**definicao):
        d = GerenteMcp.validar(definicao)
        ger = g()
        novas = ger.conectar(d)             # só salva depois de conectar de verdade
        for f in novas:
            ctx.agente.registro.adicionar(f)
        ger.salvar_config([c for c in ger.config() if c["nome"] != d["nome"]] + [d])
        return f"servidor MCP '{d['nome']}' conectado: {len(novas)} ferramenta(s): " + ", ".join(f.nome for f in novas)[:600]

    def frase(**definicao):
        try:
            d = GerenteMcp.validar(definicao)
            return f"INSTALAR/EXECUTAR um servidor MCP no seu computador: `{d['comando']} {' '.join(d['args'])}`. Ele roda como programa seu e as ferramentas dele ficam disponíveis ao Alfred (risco padrão {d['risco']}). Só aprove se confia na origem"
        except Exception as e:
            return f"adicionar servidor MCP (definição com problema, será recusada: {e})"

    def remover(nome: str):
        ger = g()
        ger.salvar_config([c for c in ger.config() if c["nome"] != nome])
        if nome in ger.clientes:
            ger.clientes.pop(nome).fechar()
        for n in [n for n in ctx.agente.registro.por_nome if n.startswith(f"mcp_{nome}_")]:
            ctx.agente.registro.por_nome.pop(n)
        return f"servidor '{nome}' removido"

    return [
        Ferramenta("mcp_listar", "Lista os servidores MCP conectados e o estado.", esquema(), Risco.VERDE, listar, lambda: "listar servidores MCP"),
        Ferramenta("mcp_adicionar", "Conecta um servidor MCP (stdio). Leia antes: ajuda_criar('mcp'). Roda um programa no computador: sempre confirma.",
                   esquema({"nome": texto("minúsculas, números, hífen ou _"), "comando": texto("só o programa, ex.: npx"), "args": {"type": "array", "items": {"type": "string"}},
                            "env": {"type": "object", "description": "variáveis; valor '@nome' vem do cofre"}, "risco": texto("A ou R"), "leitura": {"type": "array", "items": {"type": "string"}, "description": "ferramentas que só leem"}}, ["nome", "comando"]), Risco.VERMELHO, adicionar, frase, validar=lambda **d: GerenteMcp.validar(d)),
        Ferramenta("mcp_remover", "Remove um servidor MCP.", esquema({"nome": texto("nome")}, ["nome"]), Risco.AMARELO, remover, lambda nome: f"remover o servidor MCP {nome}"),
    ]
