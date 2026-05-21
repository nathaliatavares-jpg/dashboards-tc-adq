#Requires -Version 5
<#
  update_tc_dash.ps1
  Roda a query BigQuery, atualiza o dashboard HTML e faz push no GitHub.
  Agendado via Task Scheduler para rodar às 09:00, 09:30 e 13:00.
#>

$ErrorActionPreference = "Stop"
$REPO     = "C:\Users\nathtavares\dashboards-tc-adq"
$HTML     = "$REPO\dash_tc_comunicacoes.html"
$SQL_FILE = "$REPO\scripts\query.sql"
$PROJECT  = "ddme000725-g9rtvpqr28z-furyid"
$LOG      = "$REPO\logs\update_$(Get-Date -Format 'yyyyMMdd_HHmm').log"

# ── garante pasta de logs ──
New-Item -ItemType Directory -Force -Path "$REPO\logs" | Out-Null
Start-Transcript -Path $LOG

try {
    Write-Host "$(Get-Date -Format 'HH:mm:ss') Iniciando update do dashboard TC..."

    # ── 1. Roda query BigQuery ──
    $sql = Get-Content -Raw $SQL_FILE
    Write-Host "$(Get-Date -Format 'HH:mm:ss') Rodando query BigQuery (pode demorar ~10min)..."

    $csvLines = bq query `
        --project_id=$PROJECT `
        --use_legacy_sql=false `
        --format=csv `
        --max_rows=1000 `
        $sql 2>&1

    # filtra linhas de status do bq
    $csvLines = $csvLines | Where-Object { $_ -notmatch "^Waiting on|^Current status" }
    $csvText  = $csvLines -join "`n"

    # ── 2. Faz parse do CSV ──
    $rows = $csvText | ConvertFrom-Csv
    if (-not $rows -or $rows.Count -eq 0) {
        throw "Query retornou 0 linhas. Abortando."
    }
    Write-Host "$(Get-Date -Format 'HH:mm:ss') $($rows.Count) linhas recebidas."

    # ── 3. Gera JS rows ──
    $monthMap = @{
        "01"="Jan";"02"="Fev";"03"="Mar";"04"="Abr"
        "05"="Mai";"06"="Jun";"07"="Jul";"08"="Ago"
        "09"="Set";"10"="Out";"11"="Nov";"12"="Dez"
    }

    $safras = $rows | Select-Object -ExpandProperty safra -Unique | Sort-Object

    $jsRows = $rows | ForEach-Object {
        $ea = if ($_.ea_mp -eq "EA") { "'EA'" } else { "''" }
        "['$($_.safra)','$($_.flag_tc)','$($_.grupo)','$($_.flag_app_ativo)',$ea," +
        "$($_.sem_total),$($_.c13_total),$($_.c47_total),$($_.c8_total)," +
        "$($_.sem_mp),$($_.c13_mp),$($_.c47_mp),$($_.c8_mp)," +
        "$($_.sem_ml),$($_.c13_ml),$($_.c47_ml),$($_.c8_ml),$($_.total)]"
    }

    $newRaw = "const RAW = [`n" + ($jsRows -join ",`n") + ",`n];"

    $safrasJs = "[" + (($safras | ForEach-Object { "'$_'" }) -join ",") + "]"

    $labelsJs = "[" + (($safras | ForEach-Object {
        $p = $_.Split("-"); "'$($monthMap[$p[1]])/$($p[0].Substring(2))'"
    }) -join ",") + "]"

    # ── 4. Atualiza HTML ──
    $html = [System.IO.File]::ReadAllText($HTML, [System.Text.Encoding]::UTF8)

    # RAW array (regex multiline)
    $html = [regex]::Replace($html,
        '(?s)const RAW = \[.*?\n\];',
        $newRaw)

    # SAFRAS e LABELS
    $html = [regex]::Replace($html, 'const SAFRAS\s*=\s*\[[^\]]*\];', "const SAFRAS = $safrasJs;")
    $html = [regex]::Replace($html, 'const LABELS\s*=\s*\[[^\]]*\];', "const LABELS = $labelsJs;")

    # Período no header
    $today = Get-Date -Format "dd/MM/yyyy"
    $html = [regex]::Replace($html,
        'Período: 01/01/2026 – \d{2}/\d{2}/\d{4}',
        "Período: 01/01/2026 – $today")

    [System.IO.File]::WriteAllText($HTML, $html, [System.Text.Encoding]::UTF8)
    Write-Host "$(Get-Date -Format 'HH:mm:ss') HTML atualizado. Safras: $($safras -join ', ')"

    # ── 5. Git commit e push ──
    Set-Location $REPO
    git add dash_tc_comunicacoes.html

    $diff = git diff --staged --quiet; $changed = $LASTEXITCODE -ne 0
    if ($changed) {
        git commit -m "Auto-update TC dashboard $today $(Get-Date -Format 'HH:mm')"
        git push
        Write-Host "$(Get-Date -Format 'HH:mm:ss') Publicado no GitHub com sucesso."
    } else {
        Write-Host "$(Get-Date -Format 'HH:mm:ss') Sem mudanças nos dados, nada a publicar."
    }

} catch {
    Write-Error "ERRO: $_"
    exit 1
} finally {
    Stop-Transcript
}
