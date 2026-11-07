# Liga o Alfred como serviço escondido: abre sozinho quando o Windows entra e reabre se cair.
# Não precisa de administrador. Para desligar: .\parar-servico.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$pyw = Join-Path $PSScriptRoot ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $pyw)) { Write-Host "Não achei $pyw. Rode o install.ps1 primeiro."; exit 1 }
$atalho = Join-Path ([Environment]::GetFolderPath("Startup")) "Alfred.lnk"
$ws = New-Object -ComObject WScript.Shell
$lnk = $ws.CreateShortcut($atalho)
$lnk.TargetPath = $pyw
$lnk.Arguments = "-m alfred servico"
$lnk.WorkingDirectory = $PSScriptRoot
$lnk.WindowStyle = 7
$lnk.Description = "Alfred (assistente pessoal) - abre escondido quando o Windows entra"
$lnk.Save()
Write-Host "-> atalho criado em: $atalho  (abre o Alfred quando o Windows entra)"
Start-Process -FilePath $pyw -ArgumentList "-m alfred servico" -WorkingDirectory $PSScriptRoot -WindowStyle Hidden
Start-Sleep -Seconds 8
try { $ok = (Test-NetConnection 127.0.0.1 -Port 8765 -WarningAction SilentlyContinue).TcpTestSucceeded } catch { $ok = $false }
if ($ok) { Write-Host "-> Alfred no ar (escondido). Tela: http://127.0.0.1:8765/   Log: dados\alfred.log" }
else { Write-Host "-> O Alfred ainda não respondeu. Veja o fim do arquivo dados\alfred.log e me mande." }
