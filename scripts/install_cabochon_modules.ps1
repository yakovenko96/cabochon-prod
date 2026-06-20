param(
    [string]$Database = "Cabachon",
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

Write-Host "Updating Cabochon modules in database '$Database'..."
Write-Host "Order: $($modules -join ', ')"

docker exec $OdooContainer odoo `
    -d $Database `
    -u ($modules -join ",") `
    --stop-after-init `
    --db_host $DbHost `
    --db_port $DbPort `
    --db_user $DbUser `
    --db_password $DbPassword `
    --log-handler odoo.tools.convert:DEBUG

Write-Host "Cabochon modules are updated."
