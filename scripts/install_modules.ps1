<# 
.SYNOPSIS
Устанавливает или обновляет модули Cabochon Odoo.

.DESCRIPTION
Скрипт не создает базу Odoo. Сначала создайте базу, затем убедитесь, что Odoo
видит наши модули. Для этого папка addons из этого проекта должна быть указана
в настройке addons_path в файле odoo.conf.

Пример для обычной установки Odoo без Docker:
addons_path = C:\path\to\odoo\addons,C:\path\to\cabochon-prod\addons

Пример для Docker:
папка cabochon-prod\addons должна быть подключена в контейнер Odoo как
/mnt/extra-addons или другой путь, который уже есть в addons_path контейнера.

По умолчанию скрипт обновляет уже установленные модули через -u. Для новой
базы, где модули еще не установлены, используйте параметр -Install.

.EXAMPLE
powershell -ExecutionPolicy Bypass -File scripts\install_modules.ps1 -Database Cabachon -Install

Первая установка модулей в уже созданную базу Cabachon через Docker.

.EXAMPLE
powershell -ExecutionPolicy Bypass -File scripts\install_modules.ps1 -Database Cabachon

Обновление уже установленных модулей в базе Cabachon через Docker.

.EXAMPLE
powershell -ExecutionPolicy Bypass -File scripts\install_modules.ps1 -Database Cabachon -Install -OdooBin C:\path\to\odoo-bin.exe -Config C:\path\to\odoo.conf -DbHost localhost -DbPort 5432 -DbUser odoo -DbPassword 123321

Первая установка модулей без Docker через локальный odoo-bin.
#>

param(
    [string]$Database = "Cabachon",
    [switch]$Install,
    [string]$OdooBin = "",
    [string]$Config = "",
    [string]$OdooContainer = "odoo19-web",
    [string]$DbHost = "db",
    [string]$DbPort = "5432",
    [string]$DbUser = "odoo",
    [string]$DbPassword = "123321"
)

$ErrorActionPreference = "Stop"

$modules = @(
    "cabochon_base",
    "cabochon_manufacturing"
)
$moduleOperation = if ($Install) { "-i" } else { "-u" }
$actionName = if ($Install) { "Установка" } else { "Обновление" }

Write-Host "$actionName модулей Cabochon в базе '$Database'..."
Write-Host "Модули: $($modules -join ', ')"

if ($OdooBin) {
    $arguments = @(
        "-d", $Database,
        $moduleOperation, ($modules -join ","),
        "--stop-after-init",
        "--log-handler", "odoo.tools.convert:DEBUG"
    )
    if ($Config) {
        $arguments += @("--config", $Config)
    }
    if ($DbHost) {
        $arguments += @("--db_host", $DbHost)
    }
    if ($DbPort) {
        $arguments += @("--db_port", $DbPort)
    }
    if ($DbUser) {
        $arguments += @("--db_user", $DbUser)
    }
    if ($DbPassword) {
        $arguments += @("--db_password", $DbPassword)
    }
    & $OdooBin @arguments
} else {
    docker exec $OdooContainer odoo `
        -d $Database `
        $moduleOperation ($modules -join ",") `
        --stop-after-init `
        --db_host $DbHost `
        --db_port $DbPort `
        --db_user $DbUser `
        --db_password $DbPassword `
        --log-handler odoo.tools.convert:DEBUG
}

Write-Host "Модули Cabochon готовы."
