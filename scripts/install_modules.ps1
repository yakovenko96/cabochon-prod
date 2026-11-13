<#
.SYNOPSIS
Обновление Cabochon с резервной копией базы и filestore и проверкой результата.
.EXAMPLE
powershell -ExecutionPolicy Bypass -File scripts\install_modules.ps1 -Database Prod
.NOTES
Запускать на сервере после проверки релиза на копии базы. Код должен быть
подключен к контейнеру заранее; предыдущий релиз хранится отдельно для отката.
При ошибке основной контейнер остается остановленным. Автовосстановления нет.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z0-9_-]+$')][string]$Database,
    [switch]$Install,
    [string]$OdooContainer = 'odoo19-web',
    [string]$DockerNetwork = '',
    [string]$OdooBin = '',
    [string]$Config = '',
    [string]$DbHost = 'db',
    [string]$DbPort = '5432',
    [string]$DbUser = 'odoo',
    [string]$DbPassword = $env:ODOO_DB_PASSWORD,
    [string]$BackupDirectory = '',
    [switch]$ServiceStopped
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$repositoryRoot = Split-Path -Parent $PSScriptRoot
if (-not $BackupDirectory) { $BackupDirectory = Join-Path $repositoryRoot 'backups' }
$null = New-Item -ItemType Directory -Path $BackupDirectory -Force
$BackupDirectory = (Resolve-Path -LiteralPath $BackupDirectory).Path
$runId = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$backupPath = Join-Path $BackupDirectory "$Database-$runId.zip"
$logPath = Join-Path $BackupDirectory "$Database-$runId-update.log"
$connection = @('--db_host', $DbHost, '--db_port', $DbPort, '--db_user', $DbUser)
if ($DbPassword) { $connection += @('--db_password', $DbPassword) }
if ($Config) { $connection += @('--config', $Config) }
$operation = if ($Install) { '-i' } else { '-u' }
$updateArgs = @('-d', $Database, $operation, 'cabochon_base,cabochon_manufacturing', '--stop-after-init', '--no-http', '--max-cron-threads', '0') + $connection

function Invoke-NativeChecked {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Команда $Executable завершилась с кодом $LASTEXITCODE. Обновление остановлено." }
}

function Invoke-NativeLogged {
    param([string]$Executable, [string[]]$Arguments, [string]$Log)
    # Windows PowerShell 5 treats native stderr as ErrorRecords on redirection.
    # Odoo normally logs INFO to stderr; only the process exit code is failure.
    $savedPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & $Executable @Arguments *> $Log
        $commandExitCode = $LASTEXITCODE
    } finally { $ErrorActionPreference = $savedPreference }
    if ($commandExitCode -ne 0) { throw "Обновление завершилось с кодом $commandExitCode. Журнал: $Log" }
}

function Test-BackupArchive {
    param([string]$Path)
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [System.IO.Compression.ZipFile]::OpenRead($Path)
    try {
        if (-not $archive.GetEntry('dump.sql') -or -not $archive.GetEntry('manifest.json')) {
            throw 'Резервная копия не содержит dump.sql или manifest.json.'
        }
        if ($archive.GetEntry('dump.sql').Length -eq 0) { throw 'Дамп базы пуст.' }
    } finally { $archive.Dispose() }
    $hash = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
    Set-Content -LiteralPath "$Path.sha256" -Value $hash -Encoding ASCII
}

if ($OdooBin) {
    if (-not $ServiceStopped) { throw 'Для локальной Odoo остановите службу и укажите -ServiceStopped.' }
    Invoke-NativeChecked $OdooBin (@('db') + $connection + @('dump', $Database, $backupPath))
    Test-BackupArchive $backupPath
    Invoke-NativeLogged $OdooBin $updateArgs $logPath
    Write-Host "Модули обновлены. Копия: $backupPath. Запустите службу Odoo и проверьте работу пользователей."
    exit 0
}

$inspection = & docker inspect $OdooContainer
if ($LASTEXITCODE -ne 0) { throw "Не удалось прочитать контейнер $OdooContainer." }
$containerInfo = ($inspection | ConvertFrom-Json)[0]
if (-not $containerInfo.State.Running) { throw 'Основной контейнер уже остановлен. Сначала выясните причину предыдущей остановки.' }
if (-not $DockerNetwork) {
    $networks = @($containerInfo.NetworkSettings.Networks.PSObject.Properties.Name)
    if ($networks.Count -ne 1) { throw 'Укажите -DockerNetwork: сеть контейнера нельзя определить однозначно.' }
    $DockerNetwork = $networks[0]
}
$helper = "cabochon-update-$runId"
$helperCreated = $false
try {
    $createArgs = @('create', '--name', $helper, '--volumes-from', $OdooContainer, '--network', $DockerNetwork, '--entrypoint', 'sleep')
    foreach ($item in $containerInfo.Config.Env) { $createArgs += @('--env', $item) }
    if ($containerInfo.Config.User) { $createArgs += @('--user', $containerInfo.Config.User) }
    $createArgs += @($containerInfo.Image, 'infinity')
    Invoke-NativeChecked 'docker' $createArgs
    $helperCreated = $true
    Invoke-NativeChecked 'docker' @('start', $helper)
    Invoke-NativeChecked 'docker' @('stop', '--time', '120', $OdooContainer)
    Write-Host "Работа остановлена. Создается копия $Database с filestore..."
    Invoke-NativeChecked 'docker' (@('exec', $helper, 'odoo', 'db') + $connection + @('dump', $Database, '/tmp/cabochon-backup.zip'))
    Invoke-NativeChecked 'docker' @('cp', "${helper}:/tmp/cabochon-backup.zip", $backupPath)
    Test-BackupArchive $backupPath
    $metadata = @{ database = $Database; image = $containerInfo.Image; backup = $backupPath; created = $runId }
    $metadata | ConvertTo-Json | Set-Content -LiteralPath "$backupPath.json" -Encoding UTF8
    Write-Host "Копия проверена. Обновление модулей; журнал: $logPath"
    Invoke-NativeLogged 'docker' (@('exec', $helper, 'odoo') + $updateArgs) $logPath
    Invoke-NativeChecked 'docker' @('start', $OdooContainer)
    Write-Host "Модули Cabochon обновлены; контейнер запущен с новым кодом. Копия: $backupPath"
    Write-Host 'Проверьте вход и производственные действия. Запуск контейнера не заменяет функциональную проверку.'
} catch {
    Write-Error "Обновление прервано: $($_.Exception.Message). Если основной контейнер был остановлен, он намеренно не запускается. Копия (если создана): $backupPath. Не повторяйте обновление до проверки журнала." -ErrorAction Continue
    exit 1
} finally {
    if ($helperCreated) {
        & docker rm --force $helper | Out-Null
        if ($LASTEXITCODE -ne 0) { Write-Warning "Удалите временный контейнер $helper после диагностики." }
    }
}
