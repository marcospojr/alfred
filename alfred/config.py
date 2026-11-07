"""Configuração: config.toml (ou config.example.toml) + caminhos."""
import tomllib
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DADOS = BASE / "dados"
DADOS.mkdir(exist_ok=True)

PADRAO = {
    "nome": "Alfred",
    "pessoa": "",
    "idioma": "pt-BR",
    "tom": "direto e cordial",
    "modo": "supervisionado",          # observar | supervisionado | liberado
    "provedor": "groq",                # groq | openai | anthropic | gemini | openrouter | xai | ollama
    "modelo": "",                      # vazio = padrão do provedor (confira a lista do dia)
    "porta": 8765,
    "limite_diario_usd": 2.0,
    "pastas": [str(Path.home() / "Alfred-Arquivos")],
    "comandos_permitidos": ["git", "python", "python3", "node", "npm", "ls", "dir", "whoami", "date"],
    "agenda_ics": "",
    "whatsapp": {"ativo": False, "porta": 8787},
    "telegram": {"ativo": False, "dono_id": 0, "avisar_rotinas": True},
    "claude_code": {"limite_dia": 10, "tempo_max_s": 600},
    "tailscale": {"ativo": False, "endereco": "", "dono": ""},
    "email": {"ativo": False, "imap": "imap.gmail.com", "smtp": "smtp.gmail.com", "usuario": "", "permitir_envio": False},
}


def carregar() -> dict:
    cfg = {k: (v.copy() if isinstance(v, (dict, list)) else v) for k, v in PADRAO.items()}
    for nome in ("config.example.toml", "config.toml"):
        p = BASE / nome
        if p.exists():
            with p.open("rb") as f:
                dados = tomllib.load(f)
            for k, v in dados.items():
                if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                    cfg[k].update(v)
                else:
                    cfg[k] = v
    for pasta in cfg["pastas"]:
        Path(pasta).expanduser().mkdir(parents=True, exist_ok=True)
    return cfg
