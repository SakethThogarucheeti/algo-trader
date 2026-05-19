# dev.ps1 — start trading-platform (FastAPI on :8081) + trading-dashboard (Next.js on :3000)
#
# Usage: .\dev.ps1
# Stop:  Ctrl+C  (kills both child processes)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

function Wait-Port {
    param([int]$Port, [string]$Name, [int]$TimeoutSecs = 60)
    $deadline = (Get-Date).AddSeconds($TimeoutSecs)
    Write-Host ">>> Waiting for $Name on :$Port ..." -NoNewline
    while ((Get-Date) -lt $deadline) {
        try {
            $tcp = [System.Net.Sockets.TcpClient]::new("127.0.0.1", $Port)
            $tcp.Close()
            Write-Host " ready."
            return
        } catch {
            Write-Host "." -NoNewline
            Start-Sleep -Milliseconds 500
        }
    }
    Write-Host ""
    throw "ERROR: $Name did not start within ${TimeoutSecs}s"
}

# ── trading-platform ────────────────────────────────────────────────────────
Write-Host ""
Write-Host ">>> Starting trading-platform (uv run start) ..."
$platform = Start-Process -PassThru -NoNewWindow `
    -FilePath "uv" `
    -ArgumentList "run", "start" `
    -WorkingDirectory "$root\trading-platform"

Wait-Port -Port 8081 -Name "trading-platform"

# ── trading-dashboard ───────────────────────────────────────────────────────
Write-Host ""
Write-Host ">>> Starting trading-dashboard (npm run dev) ..."
$dashboard = Start-Process -PassThru -NoNewWindow `
    -FilePath "npm" `
    -ArgumentList "run", "dev" `
    -WorkingDirectory "$root\trading-dashboard"

Wait-Port -Port 3000 -Name "trading-dashboard"

Write-Host ""
Write-Host "┌─────────────────────────────────────────────┐"
Write-Host "│  trading-platform  →  http://localhost:8081 │"
Write-Host "│  trading-dashboard →  http://localhost:3000 │"
Write-Host "└─────────────────────────────────────────────┘"
Write-Host ""
Write-Host "Press Ctrl+C to stop both processes."

# Wait until Ctrl+C, then kill children
try {
    while ($true) { Start-Sleep -Seconds 5 }
} finally {
    Write-Host ""
    Write-Host ">>> Stopping processes ..."
    if (-not $platform.HasExited) { Stop-Process -Id $platform.Id -Force -ErrorAction SilentlyContinue }
    if (-not $dashboard.HasExited) { Stop-Process -Id $dashboard.Id -Force -ErrorAction SilentlyContinue }
    Write-Host ">>> Done."
}
