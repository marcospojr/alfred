# Desliga o serviço do Alfred: para o que está rodando e tira o atalho de início automático.
Set-Location $PSScriptRoot
$atalho = Join-Path ([Environment]::GetFolderPath("Startup")) "Alfred.lnk"
if (Test-Path $atalho) { Remove-Item $atalho; Write-Host "-> atalho de início automático removido" }
$procs = Get-CimInstance Win32_Process | Where-Object { ($_.Name -in @("pythonw.exe", "python.exe")) -and ($_.CommandLine -like "*-m alfred*") }
foreach ($p in $procs) { Invoke-CimMethod -InputObject $p -MethodName Terminate | Out-Null }
Write-Host "-> $($procs.Count) processo(s) do Alfred encerrado(s). Para abrir de novo com janela: iniciar.bat"
