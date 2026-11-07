"""Ferramentas para o Alfred criar, ligar, rodar e consultar automações (e encadeá-las)."""
import json
from pathlib import Path

from ..automacoes import ErroAutomacao, Motor, resumo, validar
from ..gate import Risco
from . import Ferramenta, esquema, inteiro, texto


def _motor(ctx) -> Motor:
    return ctx.agente.garantir_motor()


def criar(ctx):
    def _parse(d: dict) -> dict:
        return validar(d, ctx.agente.registro)

    def criar_auto(**definicao):
        a = _parse(definicao)
        _motor(ctx).salvar(a)
        extra = f" Segredo do webhook: {a['segredo_webhook']} (envie no cabeçalho x-webhook-secret para POST /api/webhook/{a['nome']})." if a["gatilho"]["tipo"] == "webhook" else ""
        return f"salva: {resumo(a)}{extra}"

    def frase_criar(**definicao):
        try:
            return "CRIAR AUTOMAÇÃO. " + resumo(_parse(definicao))
        except ErroAutomacao as e:
            return f"criar automação (definição com problema, ainda será recusada: {e})"

    def listar():
        return "\n".join(resumo(a) for a in _motor(ctx).listar()) or "nenhuma automação criada"

    def rodar(nome: str, entrada: str = ""):
        r = _motor(ctx).executar(nome, entrada, "pedido da pessoa")
        return json.dumps(r, ensure_ascii=False)[:3000]

    def ativar(nome: str, ativa: bool):
        m = _motor(ctx)
        a = m.obter(nome)
        if not a:
            raise ErroAutomacao(f"automação '{nome}' não existe")
        a["ativa"] = bool(ativa)
        m.salvar(a)
        return f"{nome}: {'ligada' if ativa else 'desligada'}"

    def frase_ativar(nome: str, ativa: bool):
        a = _motor(ctx).obter(nome)
        return (("LIGAR" if ativa else "desligar") + " a automação. " + resumo(a)) if a else f"ligar/desligar '{nome}' (não existe)"

    def excluir(nome: str):
        return "apagada" if _motor(ctx).excluir(nome) else "não existe"

    def historico(nome: str = "", limite: int = 10):
        log = Path(_motor(ctx).log)
        if not log.exists():
            return "nenhuma execução ainda"
        linhas = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()[-300:]]
        if nome:
            linhas = [x for x in linhas if x["nome"] == nome]
        return "\n".join(f"{x['quando']} {x['nome']} ({x['origem']}) {'ok' if x['ok'] else 'FALHOU'}: " + "; ".join(p['resumo'][:60] for p in x['passos']) for x in linhas[-max(1, min(limite, 30)):]) or "sem registros"

    return [
        Ferramenta("automacao_criar", "Cria uma automação. Leia antes: ajuda_criar('automacao'). Nasce DESLIGADA; ligar é outra ação.",
                   esquema({"nome": texto("minúsculas, números, hífen ou _"), "descricao": texto("uma frase"),
                            "gatilho": {"type": "object", "description": "ex.: {\"tipo\":\"horario\",\"hora\":\"17:00\",\"dias\":[\"sex\"]}"},
                            "passos": {"type": "array", "items": {"type": "object"}, "description": "ex.: [{\"avisar\":\"revise a semana\"}]"},
                            "permite": {"type": "array", "items": {"type": "string"}, "description": "ferramentas vermelhas que pode usar sozinha"},
                            "limite_por_hora": inteiro("execuções por hora")}, ["nome", "gatilho", "passos"]), Risco.AMARELO, criar_auto, frase_criar, validar=lambda **d: _parse(d)),
        Ferramenta("automacao_listar", "Lista as automações e se estão ligadas.", esquema(), Risco.VERDE, listar, lambda: "listar automações"),
        Ferramenta("automacao_rodar", "Roda uma automação agora (usa as mesmas permissões da automação).", esquema({"nome": texto("nome"), "entrada": texto("texto de entrada, opcional")}, ["nome"]), Risco.AMARELO, rodar,
                   lambda nome, entrada="": f"RODAR agora a automação {nome}" + (f" com a entrada: {entrada[:80]}" if entrada else "")),
        Ferramenta("automacao_ativar", "Liga ou desliga uma automação (ligada, ela roda sozinha no gatilho).", esquema({"nome": texto("nome"), "ativa": {"type": "boolean"}}, ["nome", "ativa"]), Risco.VERMELHO, ativar, frase_ativar),
        Ferramenta("automacao_excluir", "Apaga uma automação.", esquema({"nome": texto("nome")}, ["nome"]), Risco.AMARELO, excluir, lambda nome: f"apagar a automação {nome}"),
        Ferramenta("automacao_historico", "Últimas execuções das automações.", esquema({"nome": texto("filtrar por nome"), "limite": inteiro("1 a 30")}), Risco.VERDE, historico, lambda nome="", limite=10: "ver histórico de automações"),
    ]
