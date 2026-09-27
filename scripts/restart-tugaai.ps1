<#
.SYNOPSIS
    Reinicia os servidores do TugaAI (backend uvicorn + frontend vite).

.DESCRIPTION
    1. Termina os processos do TugaAI (backend em PORT e frontend em -FrontendPort),
       sem tocar em outros projectos;
    2. Arranca o backend via backend\start_windows.bat (usa o .webui_secret_key
       existente, para as sessões continuarem válidas);
    3. Arranca o frontend com `npm run dev` (PATH inclui o nvm, que não está
       configurado nesta shell) e regista os logs em %TEMP%\tugaai-logs;
    4. Confirma que ambos respondem com HTTP 200 antes de dar por concluído.

    Se encontrar processos com privilégios elevados, volta a pedir elevação
    (UAC) uma única vez.

.EXAMPLE
    .\scripts\restart-tugaai.ps1

.EXAMPLE
    .\scripts\restart-tugaai.ps1 -SkipFrontend   # só o backend
#>
[CmdletBinding()]
param(
    [switch]$SkipBackend,
    [switch]$SkipFrontend,
    # Não apresentar o prompt de UAC; apenas avisar e sair com erro.
    [switch]$NoPrompt,
    # Uso interno: já foi concedida a elevação (evita pedir duas vezes).
    [switch]$Elevated,
    [int]$FrontendPort = 5173
)

$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $ProjectRoot 'backend'
$LogDir = Join-Path $env:TEMP 'tugaai-logs'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-Step([string]$Message) { Write-Host "==> $Message" -ForegroundColor Cyan }
function Write-Ok([string]$Message) { Write-Host "    OK  $Message" -ForegroundColor Green }
function Write-Bad([string]$Message) { Write-Host "    ERRO  $Message" -ForegroundColor Red }

# ---------------------------------------------------------------- backend port
$BackendPort = 8080
$envFile = Join-Path $ProjectRoot '.env'
if (Test-Path $envFile) {
    $match = Select-String -Path $envFile -Pattern '^\s*PORT\s*=\s*(\d+)' | Select-Object -First 1
    if ($match) { $BackendPort = [int]$match.Matches[0].Groups[1].Value }
}

# ------------------------------------------------------------------ node / nvm
# O nvm não está no PATH desta shell: descobrir a instalação e adicioná-la.
$nodeDirs = @()
$nvmRoot = Join-Path $env:LOCALAPPDATA 'Author Software\nvm'
if (Test-Path (Join-Path $nvmRoot 'installs')) {
    $nodeDirs += Get-ChildItem (Join-Path $nvmRoot 'installs') -Directory |
        Sort-Object Name -Descending | ForEach-Object FullName
}
foreach ($candidate in @((Join-Path $nvmRoot '.nodejs'), (Join-Path $env:LOCALAPPDATA 'Programs\nodejs'), (Join-Path $env:ProgramFiles 'nodejs'))) {
    if (Test-Path $candidate) { $nodeDirs += $candidate }
}

$nodeExe = $null
$npmCli = $null
foreach ($dir in $nodeDirs) {
    $candidateNode = Join-Path $dir 'node.exe'
    $candidateNpm = Join-Path $dir 'node_modules\npm\bin\npm-cli.js'
    if ((Test-Path $candidateNode) -and (Test-Path $candidateNpm)) {
        $nodeExe = $candidateNode
        $npmCli = $candidateNpm
        if ($env:PATH -notlike "*$dir*") { $env:PATH = "$dir;$env:PATH" }
        break
    }
}

# ----------------------------------------------------------------- terminar
Write-Step "A terminar os processos do TugaAI ($ProjectRoot)"

# Nunca nos matamos a nós: marcar a nossa própria cadeia de ascendentes.
$allProcesses = @(Get-CimInstance Win32_Process)
$byId = @{}
foreach ($item in $allProcesses) { $byId[[int]$item.ProcessId] = $item }

$excluded = @()
$walk = [int]$PID
for ($guard = 0; $guard -lt 64 -and $byId.ContainsKey($walk); $guard++) {
    $excluded += $walk
    $walk = [int]$byId[$walk].ParentProcessId
    if ($walk -le 0) { break }
}

# Só processos que são inequivocamente os servidores do TugaAI:
#   backend  -> cmd/uvicorn/python com a bat ou o app open_webui
#   frontend -> node a correr o vite do projecto
$targets = @($allProcesses | Where-Object {
    ($_.ProcessId -notin $excluded) -and
    ($_.Name -in 'cmd.exe', 'uvicorn.exe', 'python.exe', 'npm.exe', 'node.exe') -and
    ($_.CommandLine) -and (
        (($_.Name -in 'cmd.exe', 'uvicorn.exe', 'python.exe') -and
            ($_.CommandLine -match 'start_windows\.bat|open_webui\.main:app')) -or
        (-not $SkipFrontend -and (
            (($_.Name -eq 'node.exe') -and ($_.CommandLine -match 'vite\.js')) -or
            (($_.Name -in 'cmd.exe', 'npm.exe') -and ($_.CommandLine -like "*$ProjectRoot*") -and
                ($_.CommandLine -match 'run dev|start_windows'))
        ))
    )
})

$blocked = @()

# taskkill escreve no stderr quando o processo já morreu (ex.: a árvore foi
# terminada pelo pai) e, com $ErrorActionPreference='Stop', isso derrubava o
# script — isolar a chamada.
function Stop-ProcessTree([int]$ProcessId) {
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $output = & "$env:SystemRoot\System32\taskkill.exe" /PID $ProcessId /T /F 2>&1 | Out-String
    $code = $LASTEXITCODE
    $ErrorActionPreference = $previousPreference

    if ($code -eq 0) { return @{ ok = $true; reason = '' } }
    if ($output -match 'not found') { return @{ ok = $true; reason = 'já estava terminado' } }
    return @{ ok = $false; reason = (($output -replace '\s+', ' ').Trim()) }
}

foreach ($target in $targets) {
    $result = Stop-ProcessTree -ProcessId $target.ProcessId
    if ($result.ok) {
        Write-Ok "terminado PID $($target.ProcessId) ($($target.Name)) $(if ($result.reason) { "[$($result.reason)]" })"
    } else {
        $blocked += $target
        Write-Bad "PID $($target.ProcessId) ($($target.Name)): $($result.reason)"
    }
}
if ($targets.Count -eq 0) { Write-Ok 'nenhum processo a correr' }

# Varredura final: se a porta do frontend ainda estiver ocupada por um vite,
# é uma instância duplicada — removê-la também (só quando o frontend participa).
if (-not $SkipFrontend) {
    $portOwner = Get-NetTCPConnection -State Listen -LocalPort $FrontendPort -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($ownerPid in @($portOwner)) {
        if (-not $ownerPid -or $ownerPid -in $excluded) { continue }
        $owner = $byId[[int]$ownerPid]
        if ($owner -and $owner.Name -eq 'node.exe' -and $owner.CommandLine -match 'vite\.js') {
            $result = Stop-ProcessTree -ProcessId $ownerPid
            if ($result.ok) {
                Write-Ok "terminado PID $ownerPid (vite duplicado na porta $FrontendPort)"
            } else {
                $blocked += $owner
                Write-Bad "PID $ownerPid (vite na porta $FrontendPort): $($result.reason)"
            }
        }
    }
}

if ($blocked.Count -gt 0 -and -not $Elevated) {
    if ($NoPrompt) {
        Write-Bad 'Processos elevados bloqueiam o reinício. Corra esta consola como Administrador.'
        exit 1
    }
    Write-Step 'Processos com privilégios elevados — a pedir elevação (UAC)...'
    $argList = '-NoProfile -ExecutionPolicy Bypass -File "{0}"' -f $PSCommandPath
    foreach ($name in @('SkipBackend', 'SkipFrontend', 'Elevated')) {
        if ($PSBoundParameters.ContainsKey($name)) { $argList += " -$name" }
    }
    $argList += " -FrontendPort $FrontendPort"
    Start-Process -FilePath (Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe') `
        -ArgumentList $argList -Verb RunAs
    exit 0
}
if ($blocked.Count -gt 0) {
    Write-Bad 'Ainda há processos bloqueados mesmo com elevação.'
    exit 1
}

# ----------------------------------------------------------------- arrancar
if (-not $SkipBackend) {
    Write-Step "A arrancar o backend (porta $BackendPort)..."
    Start-Process -FilePath $env:ComSpec `
        -ArgumentList '/c', "`"$(Join-Path $BackendDir 'start_windows.bat')`"" `
        -WorkingDirectory $BackendDir -WindowStyle Minimized
}

if (-not $SkipFrontend) {
    if (-not $nodeExe -or -not $npmCli) {
        Write-Bad 'Node/nvm não encontrado — frontend não pode ser arrancado.'
        exit 1
    }
    Write-Step "A arrancar o frontend (porta $FrontendPort)..."
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $feOut = Join-Path $LogDir "vite-$stamp.out.log"
    $feErr = Join-Path $LogDir "vite-$stamp.err.log"
    # Aspas obrigatórias: o caminho do nvm contém espaços ("Author Software").
    Start-Process -FilePath $nodeExe `
        -ArgumentList ('"{0}" run dev' -f $npmCli) `
        -WorkingDirectory $ProjectRoot -WindowStyle Hidden `
        -RedirectStandardOutput $feOut -RedirectStandardError $feErr
    Write-Ok "logs: $feOut"
}

# ------------------------------------------------------------------ verificar
function Wait-HttpOk([string]$Url, [int]$TimeoutSec) {
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
            if ($response.StatusCode -eq 200) { return $true }
        } catch { }
        Start-Sleep -Seconds 2
    }
    return $false
}

$failures = @()

if (-not $SkipBackend) {
    Write-Step "A aguardar http://localhost:$BackendPort/ ..."
    if (Wait-HttpOk "http://localhost:$BackendPort/" 90) {
        Write-Ok "backend em http://localhost:$BackendPort"
    } else {
        Write-Bad "backend não respondeu em http://localhost:$BackendPort"
        $failures += 'backend'
    }
}

if (-not $SkipFrontend) {
    # O `npm run dev` inclui pyodide:fetch — dar mais tempo.
    Write-Step "A aguardar http://localhost:$FrontendPort/ ..."
    if (Wait-HttpOk "http://localhost:$FrontendPort/" 120) {
        Write-Ok "frontend em http://localhost:$FrontendPort"
    } else {
        Write-Bad "frontend não respondeu em http://localhost:$FrontendPort (ver logs em $LogDir)"
        $failures += 'frontend'
    }
}

if ($failures.Count -gt 0) {
    Write-Bad ("Falhou: " + ($failures -join ', '))
    exit 1
}
Write-Host "`nTugaAI reiniciado com sucesso." -ForegroundColor Green
