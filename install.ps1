# Instalador do Alfred Kit para Windows (PowerShell). Explica cada passo e só instala com o seu sim.
# Se o PowerShell bloquear: abra o PowerShell nesta pasta e rode  Set-ExecutionPolicy -Scope Process Bypass  antes.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
function Sim($msg) { if ($env:ALFRED_INSTALL_SIM -eq "1") { return $true }; $r = Read-Host "$msg [s/N]"; return ($r -eq "s" -or $r -eq "S") }

Write-Host "== Alfred Kit: instalação =="
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  Write-Host "Falta o 'uv' (gerenciador de Python da Astral; instala o Python certo só para esta pasta)."
  if (Sim "Instalar com winget (winget install astral-sh.uv)?") { winget install --id astral-sh.uv -e; $env:Path += ";$env:LOCALAPPDATA\Microsoft\WinGet\Links;$env:USERPROFILE\.local\bin" }
  else { Write-Host "Sem o uv não dá para continuar."; exit 1 }
}
Write-Host "-> criando o ambiente Python (só nesta pasta)..."
uv venv .venv --python 3.12 --quiet
Write-Host "-> instalando as peças básicas..."
uv pip install --quiet --python .venv\Scripts\python.exe -r requirements.txt
if (-not (Test-Path config.toml)) { Copy-Item config.example.toml config.toml }
New-Item -ItemType Directory -Force dados | Out-Null
if ($env:ALFRED_INSTALL_SIM -ne "1" -and (Sim "Instalar também controle de mouse/teclado e navegador próprio (pyautogui, playwright)? Opcional.")) {
  uv pip install --quiet --python .venv\Scripts\python.exe -r requirements-extras.txt
  .venv\Scripts\python.exe -m playwright install chromium
}
Write-Host "`nAgora a chave do cérebro. Ela vai para o Gerenciador de Credenciais do Windows (nunca para um arquivo)."
$prov = (.venv\Scripts\python.exe -c "from alfred.config import carregar; print(carregar()['provedor'])").Trim()
Write-Host "Provedor no config.toml: $prov  (Anthropic: crie a chave em https://console.anthropic.com/settings/keys)"
if ($env:ALFRED_INSTALL_SIM -ne "1" -and (Sim "Guardar a chave de '$prov' agora?")) { .venv\Scripts\python.exe -m alfred chave $prov }
.venv\Scripts\python.exe -m alfred testar
Write-Host "`nChamada de teste ao cérebro (custa uma fração de centavo):"
.venv\Scripts\python.exe -m alfred oi
Write-Host "`nPronto. Para abrir: dê dois cliques em iniciar.bat"
