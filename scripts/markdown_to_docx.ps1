param(
    [Parameter(Mandatory = $true)]
    [string]$InputPath,
    [Parameter(Mandatory = $true)]
    [string]$OutputPath
)

$ErrorActionPreference = "Stop"
$inputFile = (Resolve-Path -LiteralPath $InputPath).Path
$outputFile = [System.IO.Path]::GetFullPath($OutputPath)
$markdown = Get-Content -Raw -Encoding UTF8 -LiteralPath $inputFile

function Convert-InlineMarkdown([string]$text) {
    $encoded = [System.Net.WebUtility]::HtmlEncode($text)
    $encoded = [regex]::Replace($encoded, '\*\*(.+?)\*\*', '<strong>$1</strong>')
    $encoded = [regex]::Replace($encoded, '`(.+?)`', '<code>$1</code>')
    return $encoded
}

$lines = $markdown -split "`r?`n"
$html = New-Object System.Text.StringBuilder
[void]$html.AppendLine('<!DOCTYPE html><html><head><meta charset="utf-8"><style>')
[void]$html.AppendLine('@page { size: A4; margin: 2cm; } body { font-family: Calibri, Arial, sans-serif; font-size: 11pt; line-height: 1.25; color: #222; } h1 { font-size: 20pt; color: #17365d; } h2 { font-size: 16pt; color: #1f4e78; margin-top: 18pt; } h3 { font-size: 13pt; color: #2f5597; margin-top: 14pt; } p { margin: 5pt 0; } ul, ol { margin: 4pt 0 8pt 24pt; } li { margin: 2pt 0; } table { border-collapse: collapse; width: 100%; margin: 8pt 0; font-size: 9pt; } th { background: #d9eaf7; font-weight: bold; } th, td { border: 1px solid #7f8c8d; padding: 5px; vertical-align: top; } code { font-family: Consolas, monospace; background: #f2f2f2; padding: 1px 3px; }')
[void]$html.AppendLine('</style></head><body>')

$listType = $null
$inTable = $false
for ($i = 0; $i -lt $lines.Count; $i++) {
    $line = $lines[$i]
    if ($line -match '^\|.*\|$') {
        if (($i + 1) -lt $lines.Count -and $lines[$i + 1] -match '^\|[\s:|-]+\|$') {
            if ($listType) { [void]$html.AppendLine("</$listType>"); $listType = $null }
            [void]$html.AppendLine('<table>')
            $cells = $line.Trim('|').Split('|')
            [void]$html.Append('<tr>')
            foreach ($cell in $cells) { [void]$html.Append('<th>' + (Convert-InlineMarkdown $cell.Trim()) + '</th>') }
            [void]$html.AppendLine('</tr>')
            $inTable = $true
            $i++
            continue
        }
        if ($inTable) {
            $cells = $line.Trim('|').Split('|')
            [void]$html.Append('<tr>')
            foreach ($cell in $cells) { [void]$html.Append('<td>' + (Convert-InlineMarkdown $cell.Trim()) + '</td>') }
            [void]$html.AppendLine('</tr>')
            continue
        }
    }
    if ($inTable) { [void]$html.AppendLine('</table>'); $inTable = $false }

    if ($line -match '^(#{1,3})\s+(.+)$') {
        if ($listType) { [void]$html.AppendLine("</$listType>"); $listType = $null }
        $level = $matches[1].Length
        [void]$html.AppendLine("<h$level>$(Convert-InlineMarkdown $matches[2])</h$level>")
    } elseif ($line -match '^[-*]\s+(.+)$') {
        if ($listType -ne 'ul') { if ($listType) { [void]$html.AppendLine("</$listType>") }; [void]$html.AppendLine('<ul>'); $listType = 'ul' }
        [void]$html.AppendLine('<li>' + (Convert-InlineMarkdown $matches[1]) + '</li>')
    } elseif ($line -match '^\d+\.\s+(.+)$') {
        if ($listType -ne 'ol') { if ($listType) { [void]$html.AppendLine("</$listType>") }; [void]$html.AppendLine('<ol>'); $listType = 'ol' }
        [void]$html.AppendLine('<li>' + (Convert-InlineMarkdown $matches[1]) + '</li>')
    } elseif ([string]::IsNullOrWhiteSpace($line)) {
        if ($listType) { [void]$html.AppendLine("</$listType>"); $listType = $null }
    } else {
        if ($listType) { [void]$html.AppendLine("</$listType>"); $listType = $null }
        [void]$html.AppendLine('<p>' + (Convert-InlineMarkdown $line) + '</p>')
    }
}
if ($listType) { [void]$html.AppendLine("</$listType>") }
if ($inTable) { [void]$html.AppendLine('</table>') }
[void]$html.AppendLine('</body></html>')

$tempHtml = Join-Path ([System.IO.Path]::GetTempPath()) ("cabochon-guide-" + [guid]::NewGuid().ToString('N') + '.html')
[System.IO.File]::WriteAllText($tempHtml, $html.ToString(), [System.Text.UTF8Encoding]::new($true))

$word = $null
$document = $null
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
    $document = $word.Documents.Open($tempHtml)
    $document.SaveAs2($outputFile, 16)
} finally {
    if ($document) { $document.Close($false) }
    if ($word) { $word.Quit() }
    Remove-Item -LiteralPath $tempHtml -Force -ErrorAction SilentlyContinue
}

Write-Output $outputFile
