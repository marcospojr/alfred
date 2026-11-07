"""Arquivos: só dentro das pastas que a pessoa listou no config.toml. Apagar = lixeira."""
import os
import shutil
from pathlib import Path

from ..gate import Risco
from . import Ferramenta, esquema, inteiro, texto

BLOQUEADOS = {".env", ".ssh", ".gnupg", ".aws", "id_rsa", "id_ed25519", "keychains", "login data", "cookies", "wallet.dat"}
EXT_BLOQUEADAS = {".pem", ".key", ".p12", ".pfx", ".kdbx", ".env"}


def _raizes(cfg) -> list[Path]:
    return [Path(p).expanduser().resolve() for p in cfg["pastas"]]


def caminho_seguro(cfg, caminho: str) -> Path:
    """Resolve o caminho real (derruba '..' e atalhos) e exige estar dentro de uma pasta permitida."""
    raizes = _raizes(cfg)
    p = Path(caminho).expanduser()
    if not p.is_absolute():
        p = raizes[0] / p
    real = p.resolve()
    if not any(real == r or r in real.parents for r in raizes):
        raise PermissionError(f"fora das pastas permitidas: {real}")
    partes = {x.lower() for x in real.parts}
    if partes & BLOQUEADOS or real.suffix.lower() in EXT_BLOQUEADAS:
        raise PermissionError("arquivo sensível bloqueado")
    return real


def criar(ctx):
    cfg = ctx.cfg

    def listar_pasta(caminho: str = "."):
        p = caminho_seguro(cfg, caminho)
        itens = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))[:200]
        return "\n".join(f"{'[pasta] ' if i.is_dir() else ''}{i.name}" + ("" if i.is_dir() else f"  ({i.stat().st_size} bytes)") for i in itens) or "(vazia)"

    def ler_arquivo(caminho: str, max_caracteres: int = 20000):
        p = caminho_seguro(cfg, caminho)
        if p.stat().st_size > 5_000_000:
            raise ValueError("arquivo grande demais (>5 MB)")
        dados = p.read_bytes()
        if b"\x00" in dados[:2048]:
            raise ValueError("arquivo binário: não leio como texto")
        return dados.decode("utf-8", errors="replace")[: max(1, min(max_caracteres, 50000))]

    def buscar_arquivos(termo: str, pasta: str = "."):
        raiz, achados, t = caminho_seguro(cfg, pasta), [], termo.lower()
        for dp, dn, fn in os.walk(raiz):
            dn[:] = [d for d in dn if d.lower() not in BLOQUEADOS and not d.startswith(".")]
            for n in fn:
                if t in n.lower():
                    achados.append(str(Path(dp) / n))
                    if len(achados) >= 100:
                        return "\n".join(achados) + "\n(mostrando os 100 primeiros)"
        return "\n".join(achados) or "nada encontrado"

    def escrever_arquivo(caminho: str, conteudo: str, sobrescrever: bool = False):
        p = caminho_seguro(cfg, caminho)
        if p.exists() and not sobrescrever:
            raise FileExistsError("já existe; peça confirmação para sobrescrever")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(conteudo, encoding="utf-8")
        return f"escrito: {p} ({len(conteudo)} caracteres)"

    def mover_para_lixeira(caminho: str):
        p = caminho_seguro(cfg, caminho)
        try:
            from send2trash import send2trash
            send2trash(str(p))
        except ImportError:
            quarentena = Path.home() / ".Trash" if Path.home().joinpath(".Trash").exists() else Path(cfg["pastas"][0]).expanduser() / "_lixeira"
            quarentena.mkdir(parents=True, exist_ok=True)
            shutil.move(str(p), str(quarentena / p.name))
        return f"movido para a lixeira: {p.name}"

    def mover_arquivo(origem: str, destino: str):
        a, b = caminho_seguro(cfg, origem), caminho_seguro(cfg, destino)
        if b.is_dir():
            b = b / a.name
        if b.exists():
            raise FileExistsError("o destino já existe")
        shutil.move(str(a), str(b))
        return f"movido: {a.name} -> {b}"

    P = {"caminho": texto("caminho relativo à primeira pasta permitida, ou absoluto dentro das permitidas")}
    return [
        Ferramenta("listar_pasta", "Lista os arquivos de uma pasta permitida.", esquema({"caminho": P["caminho"]}), Risco.VERDE,
                   listar_pasta, lambda caminho=".": f"listar {caminho}"),
        Ferramenta("ler_arquivo", "Lê um arquivo de texto de uma pasta permitida.", esquema({**P, "max_caracteres": inteiro("limite de caracteres")}, ["caminho"]), Risco.VERDE,
                   ler_arquivo, lambda caminho, max_caracteres=0: f"ler {caminho}", externo=True),
        Ferramenta("buscar_arquivos", "Procura arquivos pelo nome dentro das pastas permitidas.", esquema({"termo": texto("parte do nome"), "pasta": P["caminho"]}, ["termo"]), Risco.VERDE,
                   buscar_arquivos, lambda termo, pasta=".": f"buscar '{termo}' em {pasta}"),
        Ferramenta("escrever_arquivo", "Cria um arquivo de texto novo (não sobrescreve sem pedir).", esquema({**P, "conteudo": texto("texto do arquivo"), "sobrescrever": {"type": "boolean"}}, ["caminho", "conteudo"]), Risco.AMARELO,
                   escrever_arquivo, lambda caminho, conteudo, sobrescrever=False: f"{'sobrescrever' if sobrescrever else 'criar'} o arquivo {caminho} ({len(conteudo)} caracteres)"),
        Ferramenta("mover_para_lixeira", "Move um arquivo ou pasta para a lixeira (nunca apaga de vez).", esquema(P, ["caminho"]), Risco.AMARELO,
                   mover_para_lixeira, lambda caminho: f"mover para a lixeira: {caminho}"),
        Ferramenta("mover_arquivo", "Move ou renomeia dentro das pastas permitidas.", esquema({"origem": P["caminho"], "destino": P["caminho"]}, ["origem", "destino"]), Risco.AMARELO,
                   mover_arquivo, lambda origem, destino: f"mover {origem} para {destino}"),
    ]
