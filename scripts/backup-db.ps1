<#
.SYNOPSIS
  备份 SQLite 数据库到 data\backups\

.EXAMPLE
  .\scripts\backup-db.ps1
  .\scripts\backup-db.ps1 -Keep 20
#>
param([int]$Keep = 10)

$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $root '.venv\Scripts\python.exe'

if (-not (Test-Path $py)) {
  Write-Host "找不到虚拟环境：$py" -ForegroundColor Red
  exit 1
}

& $py (Join-Path $PSScriptRoot 'backup_db.py') --keep $Keep
exit $LASTEXITCODE
