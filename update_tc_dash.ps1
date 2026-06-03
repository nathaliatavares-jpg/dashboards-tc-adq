#Requires -Version 5
<#
  update_tc_dash.ps1
  Atualiza os dashboards TC ADQ via Python e faz push no GitHub.
  Agendado via Task Scheduler para rodar as 09:00, 09:30 e 13:00.
#>

$ErrorActionPreference = "Stop"
$REPO = "C:\Users\nathtavares\dashboards-tc-adq"

New-Item -ItemType Directory -Force -Path "$REPO\logs" | Out-Null
$LOG = "$REPO\logs\update_$(Get-Date -Format 'yyyyMMdd_HHmm').log"
Start-Transcript -Path $LOG

try {
    Write-Host "$(Get-Date -Format 'HH:mm:ss') Iniciando update dos dashboards TC..."
    Set-Location $REPO

    # 1. Atualiza dash_tc_comunicacoes.html
    Write-Host "$(Get-Date -Format 'HH:mm:ss') Atualizando dash_tc_comunicacoes.html..."
    python scripts\update_tc_dash.py
    if ($LASTEXITCODE -ne 0) { throw "update_tc_dash.py falhou com codigo $LASTEXITCODE" }

    # 2. Atualiza daily.html
    Write-Host "$(Get-Date -Format 'HH:mm:ss') Atualizando daily.html..."
    python scripts\update_daily_dash.py
    if ($LASTEXITCODE -ne 0) { throw "update_daily_dash.py falhou com codigo $LASTEXITCODE" }

    # 3. Atualiza uso.html
    Write-Host "$(Get-Date -Format 'HH:mm:ss') Atualizando uso.html..."
    python scripts\update_uso_dash.py
    if ($LASTEXITCODE -ne 0) { throw "update_uso_dash.py falhou com codigo $LASTEXITCODE" }

    # 4. Git commit e push se houve mudanca
    git add dash_tc_comunicacoes.html daily.html uso.html
    git diff --staged --quiet
    if ($LASTEXITCODE -ne 0) {
        $msg = "Auto-update TC dashboard $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
        git commit -m $msg
        git push
        Write-Host "$(Get-Date -Format 'HH:mm:ss') Publicado no GitHub com sucesso."
    } else {
        Write-Host "$(Get-Date -Format 'HH:mm:ss') Sem mudancas nos dados, nada a publicar."
    }

} catch {
    Write-Error "ERRO: $_"
    exit 1
} finally {
    Stop-Transcript
}
