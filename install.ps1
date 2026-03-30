param(
    [switch]$NonInteractive,
    [ValidateSet("postgres", "sqlite")]
    [string]$Mode,
    [switch]$StartServices
)

$ErrorActionPreference = "Stop"

Set-Location -LiteralPath $PSScriptRoot

function Read-Default([string]$Prompt, [string]$DefaultValue, [switch]$Secret) {
    if ($NonInteractive) {
        return $DefaultValue
    }

    $fullPrompt = if ($DefaultValue) { "$Prompt [$DefaultValue]" } else { $Prompt }
    if ($Secret) {
        $secure = Read-Host -Prompt $fullPrompt -AsSecureString
        $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        try {
            $value = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
        } finally {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
        }
        if ([string]::IsNullOrWhiteSpace($value)) { return $DefaultValue }
        return $value
    }

    $value = Read-Host -Prompt $fullPrompt
    if ([string]::IsNullOrWhiteSpace($value)) { return $DefaultValue }
    return $value
}

function New-RandomSecret([int]$Length = 48) {
    $chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
    -join (1..$Length | ForEach-Object { $chars[(Get-Random -Minimum 0 -Maximum $chars.Length)] })
}

function Set-OrAddLine([string[]]$Lines, [string]$Key, [string]$Value) {
    $prefix = "$Key="
    $updated = $false
    for ($i = 0; $i -lt $Lines.Count; $i++) {
        if ($Lines[$i].StartsWith($prefix)) {
            $Lines[$i] = "$Key=$Value"
            $updated = $true
        }
    }
    if (-not $updated) {
        $Lines += "$Key=$Value"
    }
    return @($Lines)
}

if (-not $Mode) {
    if ($NonInteractive) {
        $Mode = "postgres"
    } else {
        Write-Host ""
        Write-Host "Choose storage mode:"
        Write-Host "1. PostgreSQL with Docker (recommended)"
        Write-Host "2. SQLite file mode"
        $choice = Read-Host "Enter 1 or 2"
        $Mode = if ($choice -eq "2") { "sqlite" } else { "postgres" }
    }
}

$appPort = Read-Default "App port" "8000"
$adminUsername = Read-Default "Bootstrap admin username" "admin"
$adminPassword = Read-Default "Bootstrap admin password" "admin123" -Secret
$systemApiBase = Read-Default "Bootstrap system API base" "https://api.openai.com/v1"
$systemApiKey = Read-Default "Bootstrap system API key" ""
$systemModel = Read-Default "Bootstrap system model" "gpt-4o"
$secretKey = Read-Default "App SECRET_KEY" (New-RandomSecret)
$setupWizardEnabled = "true"

$envLines = @()
if (Test-Path -LiteralPath ".env") {
    $envLines = Get-Content -LiteralPath ".env"
}

if ($Mode -eq "postgres") {
    $postgresDb = Read-Default "PostgreSQL database name" "ai_chat"
    $postgresUser = Read-Default "PostgreSQL username" "ai_chat"
    $postgresPassword = Read-Default "PostgreSQL password" "change-me" -Secret
    $postgresPort = Read-Default "PostgreSQL host port" "5432"

    $databaseUrl = "postgresql://${postgresUser}:${postgresPassword}@postgres:5432/${postgresDb}"

    $envLines = Set-OrAddLine $envLines "DATABASE_URL" $databaseUrl
    $envLines = Set-OrAddLine $envLines "APP_PORT" $appPort
    $envLines = Set-OrAddLine $envLines "POSTGRES_DB" $postgresDb
    $envLines = Set-OrAddLine $envLines "POSTGRES_USER" $postgresUser
    $envLines = Set-OrAddLine $envLines "POSTGRES_PASSWORD" $postgresPassword
    $envLines = Set-OrAddLine $envLines "POSTGRES_PORT" $postgresPort
} else {
    $databaseUrl = "sqlite:///data/chat.db"
    $envLines = Set-OrAddLine $envLines "DATABASE_URL" $databaseUrl
    $envLines = Set-OrAddLine $envLines "APP_PORT" $appPort
}

$envLines = Set-OrAddLine $envLines "ENV" "development"
$envLines = Set-OrAddLine $envLines "SECRET_KEY" $secretKey
$envLines = Set-OrAddLine $envLines "BOOTSTRAP_ADMIN_USERNAME" $adminUsername
$envLines = Set-OrAddLine $envLines "BOOTSTRAP_ADMIN_PASSWORD" $adminPassword
$envLines = Set-OrAddLine $envLines "BOOTSTRAP_SYSTEM_API_BASE" $systemApiBase
$envLines = Set-OrAddLine $envLines "BOOTSTRAP_SYSTEM_API_KEY" $systemApiKey
$envLines = Set-OrAddLine $envLines "BOOTSTRAP_SYSTEM_MODEL" $systemModel
$envLines = Set-OrAddLine $envLines "SETUP_WIZARD_ENABLED" $setupWizardEnabled

Set-Content -LiteralPath ".env" -Value $envLines

Write-Host ""
Write-Host "Wrote .env for mode: $Mode"
Write-Host "DATABASE_URL=$databaseUrl"

if ($Mode -eq "postgres") {
    $dockerExists = $null -ne (Get-Command docker -ErrorAction SilentlyContinue)
    if (-not $dockerExists) {
        Write-Warning "Docker was not found. Install Docker Desktop, then run: docker compose up -d"
        exit 0
    }

    if ($StartServices -or $NonInteractive) {
        docker compose up -d --build
        Write-Host "Started app + postgres with Docker."
        exit 0
    }

    $shouldStart = Read-Default "Start app + postgres with docker compose now? (y/n)" "y"
    if ($shouldStart -match '^(y|Y)') {
        docker compose up -d --build
        Write-Host "Started app + postgres with Docker."
    } else {
        Write-Host "Run 'docker compose up -d --build' when ready."
    }
    exit 0
}

Write-Host "SQLite mode is ready."
Write-Host "Create a venv, install requirements, then run: py -3.13 main.py"
