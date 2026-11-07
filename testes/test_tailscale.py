"""Painel pelo Tailscale: só a conta do dono entra; sem conta (Funnel/internet) ou outra conta -> 403; desligado -> recusa."""
import json

import pytest

from test_tudo import Falso, ctx  # noqa: F401  (fixture)

END = "beaesthetic.tail1234.ts.net"


@pytest.fixture()
def cliente(ctx):
    from fastapi.testclient import TestClient
    from alfred.agente import Agente
    from alfred.servidor import criar_app
    ctx.cfg["tailscale"] = {"ativo": True, "endereco": END, "dono": "Marcos@Gmail.com"}
    app = criar_app(Agente(ctx, Falso([])), token="tok")
    with TestClient(app, base_url="http://127.0.0.1:8765") as c:
        yield c, ctx


def test_dono_abre_painel_e_api(cliente):
    c, _ = cliente
    cab = {"host": END, "tailscale-user-login": "marcos@gmail.com"}
    r = c.get("/", headers=cab)
    assert r.status_code == 200 and "tok" in r.text
    assert c.get("/api/estado", headers={**cab, "x-alfred": "tok"}).status_code == 200
    assert c.get("/api/estado", headers={**cab, "x-alfred": "errado"}).status_code == 401     # o token continua valendo


@pytest.mark.parametrize("login", ["", "outra.pessoa@gmail.com"])
def test_outros_recusados(cliente, login):
    c, _ = cliente
    cab = {"host": END}
    if login:
        cab["tailscale-user-login"] = login
    r = c.get("/", headers=cab)
    assert r.status_code == 403 and "tok" not in r.text


def test_desligado_recusa_endereco(cliente):
    c, ctx = cliente
    ctx.cfg["tailscale"]["ativo"] = False
    assert c.get("/", headers={"host": END, "tailscale-user-login": "marcos@gmail.com"}).status_code == 403


def test_local_continua_funcionando(cliente):
    c, _ = cliente
    assert c.get("/").status_code == 200


def test_proxy_que_troca_o_host_tambem_e_conferido(cliente):
    """Se o tailscale serve mandar Host 127.0.0.1, o X-Forwarded-For e a conta ainda denunciam que veio de fora."""
    c, ctx = cliente
    assert c.get("/", headers={"x-forwarded-for": "100.64.0.5"}).status_code == 403                     # Funnel: sem conta
    assert c.get("/", headers={"x-forwarded-for": "100.64.0.5", "tailscale-user-login": "marcos@gmail.com"}).status_code == 200
    ctx.cfg["tailscale"]["ativo"] = False
    assert c.get("/", headers={"x-forwarded-for": "100.64.0.5", "tailscale-user-login": "marcos@gmail.com"}).status_code == 403
