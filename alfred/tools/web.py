"""Web: ler páginas e buscar. Bloqueia endereços internos (SSRF). O que vem de fora é DADO, nunca ordem."""
import html
import ipaddress
import re
import socket
from urllib.parse import quote_plus, unquote, urlparse, parse_qs

import httpx

from ..gate import Risco
from . import Ferramenta, esquema, texto

UA = {"User-Agent": "Mozilla/5.0 (AlfredKit; assistente pessoal)"}


def url_publica(url: str) -> str:
    u = urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ValueError("só links http(s)")
    for info in socket.getaddrinfo(u.hostname, None):
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise PermissionError("endereço interno bloqueado")
    return url


def html_para_texto(h: str) -> str:
    h = re.sub(r"(?is)<(script|style|noscript|svg).*?</\1>", " ", h)
    h = re.sub(r"(?s)<br\s*/?>|</p>|</div>|</li>|</h\d>", "\n", h)
    t = html.unescape(re.sub(r"<[^>]+>", " ", h))
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n\n", t)).strip()


def criar(ctx):
    def ler_pagina(url: str):
        url_publica(url)
        with httpx.Client(follow_redirects=True, timeout=15, headers=UA, max_redirects=4) as c:
            r = c.get(url)
            url_publica(str(r.url))
            r.raise_for_status()
            return html_para_texto(r.text[:1_500_000])[:8000]

    def buscar_web(consulta: str):
        r = httpx.post("https://html.duckduckgo.com/html/", data={"q": consulta}, headers=UA, timeout=15, follow_redirects=True)
        r.raise_for_status()
        achados = []
        for m in re.finditer(r'(?s)class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?class="result__snippet"[^>]*>(.*?)</a>', r.text):
            link, titulo, trecho = m.groups()
            q = parse_qs(urlparse(link).query).get("uddg")
            achados.append(f"- {html_para_texto(titulo)}\n  {unquote(q[0]) if q else link}\n  {html_para_texto(trecho)}")
            if len(achados) >= 6:
                break
        return "\n".join(achados) or "sem resultados (o buscador pode ter mudado o formato)"

    return [
        Ferramenta("ler_pagina", "Baixa uma página pública e devolve o texto.", esquema({"url": texto("endereço completo")}, ["url"]), Risco.VERDE, ler_pagina, lambda url: f"ler a página {url}", externo=True),
        Ferramenta("buscar_web", "Busca na web (DuckDuckGo) e devolve títulos, links e trechos.", esquema({"consulta": texto("o que buscar")}, ["consulta"]), Risco.VERDE, buscar_web, lambda consulta: f"buscar na web: {consulta}", externo=True),
    ]
