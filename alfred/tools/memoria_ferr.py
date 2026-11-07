"""Ferramentas de memória: lembrar, buscar, listar e esquecer."""
from ..gate import Risco
from . import Ferramenta, esquema, texto


def criar(ctx):
    m = ctx.memoria

    def lembrar(chave: str, valor: str):
        m.lembrar(chave, valor)
        return f"guardei: {chave} = {valor}"

    def buscar(consulta: str):
        r = m.buscar(consulta, 5)
        return "\n".join(f"{q[:10]} ({quem}): {t}" for q, quem, t in r) or "não achei nada sobre isso"

    def listar():
        return "\n".join(f"{k}: {v}" for k, v in m.fatos()) or "(nenhum fato guardado)"

    def esquecer(chave: str):
        return f"{m.esquecer(chave)} item(ns) apagado(s)"

    return [
        Ferramenta("lembrar", "Guarda um fato curto e durável sobre a pessoa ('restaurante favorito' = 'Ostradamus').", esquema({"chave": texto("nome do fato"), "valor": texto("valor")}, ["chave", "valor"]), Risco.AMARELO, lembrar, lambda chave, valor: f"guardar na memória: {chave} = {valor}"),
        Ferramenta("buscar_memoria", "Busca em conversas antigas (funciona sem acento).", esquema({"consulta": texto("palavras")}, ["consulta"]), Risco.VERDE, buscar, lambda consulta: f"buscar na memória: {consulta}"),
        Ferramenta("listar_fatos", "Lista tudo que está guardado sobre a pessoa.", esquema(), Risco.VERDE, listar, lambda: "listar a memória"),
        Ferramenta("esquecer", "Apaga um fato da memória.", esquema({"chave": texto("nome do fato")}, ["chave"]), Risco.AMARELO, esquecer, lambda chave: f"apagar da memória: {chave}"),
    ]
