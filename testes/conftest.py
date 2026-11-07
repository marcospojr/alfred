"""Os testes nunca escrevem nos arquivos reais do Marcos nem rodam as rotinas dele (bom-dia, fechamento)."""
import importlib

import pytest

from alfred import cota, gate, rotinas


@pytest.fixture(autouse=True)
def _isolar_dados(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "LOG", tmp_path / "auditoria.jsonl")
    monkeypatch.setattr(cota, "ARQ", tmp_path / "cota.json")
    monkeypatch.setattr(rotinas, "PASTAS", [])
    import alfred.servidor
    monkeypatch.setattr(alfred.servidor, "BACKUP_AUTOMATICO", False)    # backup de verdade só no Alfred rodando                 # sem as rotinas de verdade da pasta rotinas/
    for nome in ("alfred.servidor", "alfred.automacoes", "alfred.mcp_servidor", "alfred.tools.tarefas", "alfred.tools.agenda",
                 "alfred.servico", "alfred.rotinas"):
        mod = importlib.import_module(nome)
        if hasattr(mod, "DADOS"):
            monkeypatch.setattr(mod, "DADOS", tmp_path)
