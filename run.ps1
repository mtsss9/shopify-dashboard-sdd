# Launch the Shopify Data Explorer. Implements specs/003-dashboard-ui.md §6.6
# (plan §3, decisions U1, U8, U9).
#
# Reads KEY=VALUE pairs from .env in the project root, sets them for the app
# (.env always wins over the session), and runs Streamlit. Never prints a value.
# Dot-sourcing this file (`. .\run.ps1`) only defines the functions, for tests.

function Read-DotEnv {
    <# Parse a .env file into an ordered dictionary (decision U8). #>
    param([Parameter(Mandatory = $true)][string]$Path)

    $pairs = [ordered]@{}
    $lineNumber = 0
    foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
        $lineNumber++
        $text = $line.Trim()
        if ($text -eq '' -or $text.StartsWith('#')) { continue }

        $eq = $text.IndexOf('=')
        if ($eq -lt 1) {
            # Name the line number only: the line may hold a secret.
            throw "Line $lineNumber of .env is not a KEY=VALUE line."
        }
        $key = $text.Substring(0, $eq).Trim()
        $value = $text.Substring($eq + 1).Trim()
        if ($value.Length -ge 2 -and ($value[0] -eq '"' -or $value[0] -eq "'") -and $value[-1] -eq $value[0]) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        $pairs[$key] = $value
    }
    return $pairs
}

function Set-DotEnv {
    <# Set each pair in this process, replacing any session value (.env wins). #>
    param([Parameter(Mandatory = $true)][System.Collections.IDictionary]$Pairs)

    foreach ($key in $Pairs.Keys) {
        Set-Item -LiteralPath "env:$key" -Value $Pairs[$key]
    }
}

if ($MyInvocation.InvocationName -eq '.') { return }

$ErrorActionPreference = 'Stop'

$envFile = Join-Path $PSScriptRoot '.env'
if (-not (Test-Path -LiteralPath $envFile -PathType Leaf)) {
    Write-Host '.env is missing from the project root. Create it by copying .env.example and filling in the values.'
    exit 1
}

try {
    $pairs = Read-DotEnv -Path $envFile
} catch {
    Write-Host $_.Exception.Message
    exit 1
}

$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    Write-Host '.venv is missing. Create it with: python -m venv .venv; .\.venv\Scripts\pip install -r requirements.txt'
    exit 1
}

# Remember the session's values so the .env values do not outlive the app.
$names = @($pairs.Keys) + 'PYTHONPATH'
$saved = @{}
foreach ($name in $names) { $saved[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }

try {
    Set-DotEnv -Pairs $pairs
    $src = Join-Path $PSScriptRoot 'src'
    if ($saved['PYTHONPATH']) { $env:PYTHONPATH = "$src;$($saved['PYTHONPATH'])" } else { $env:PYTHONPATH = $src }

    & $python -m streamlit run (Join-Path $PSScriptRoot 'src\shopify_dashboard\app.py') @args
    $code = $LASTEXITCODE
} finally {
    foreach ($name in $names) { [Environment]::SetEnvironmentVariable($name, $saved[$name], 'Process') }
}
exit $code
