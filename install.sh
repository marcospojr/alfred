#!/bin/bash
# Instalador do Alfred Kit para Mac (e Linux). Explica cada passo e só instala com o seu sim.
set -e
cd "$(dirname "$0")"
sim() { [ "$ALFRED_INSTALL_SIM" = "1" ] && return 0; read -r -p "$1 [s/N] " r; [ "$r" = "s" ] || [ "$r" = "S" ]; }

echo "== Alfred Kit: instalação =="
if ! command -v uv >/dev/null 2>&1; then
  echo "Falta o 'uv' (gerenciador de Python da Astral; instala o Python certo só para esta pasta)."
  if command -v brew >/dev/null 2>&1 && sim "Instalar com Homebrew (brew install uv)?"; then brew install uv
  elif sim "Instalar com o instalador oficial (https://astral.sh/uv/install.sh)? Leia o script antes se quiser."; then curl -LsSf https://astral.sh/uv/install.sh | sh; export PATH="$HOME/.local/bin:$PATH"
  else echo "Sem o uv não dá para continuar. Instale e rode de novo."; exit 1; fi
fi
echo "-> criando o ambiente Python (só nesta pasta)..."
uv venv .venv --python 3.12 --quiet
echo "-> instalando as peças básicas (fastapi, httpx, keyring, send2trash...)..."
uv pip install --quiet --python .venv/bin/python -r requirements.txt
[ -f config.toml ] || cp config.example.toml config.toml
mkdir -p dados
if [ "$ALFRED_INSTALL_SIM" != "1" ] && sim "Instalar também controle de mouse/teclado e navegador próprio (pyautogui, playwright)? Opcional."; then
  uv pip install --quiet --python .venv/bin/python -r requirements-extras.txt
  .venv/bin/python -m playwright install chromium || true
fi
echo
echo "Agora a chave do cérebro. Ela vai para o Chaveiro do Mac (nunca para um arquivo)."
echo "Grátis: crie em https://console.groq.com/keys (Groq, com Q). Outros: edite 'provedor' no config.toml."
if [ "$ALFRED_INSTALL_SIM" != "1" ] && sim "Guardar a chave agora?"; then .venv/bin/python -m alfred chave "$(.venv/bin/python -c 'from alfred.config import carregar;print(carregar()["provedor"])')"; fi
.venv/bin/python -m alfred testar || true
chmod +x iniciar.command 2>/dev/null || true
echo; echo "Pronto. Para abrir: dê dois cliques em iniciar.command (ou: .venv/bin/python -m alfred)"
