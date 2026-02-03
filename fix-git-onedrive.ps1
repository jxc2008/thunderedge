# Script to fix OneDrive Git lock issue
Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host "Fixing OneDrive Git Lock Issue" -ForegroundColor Cyan
Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host ""

# Step 1: Try to stop OneDrive sync temporarily
Write-Host "Step 1: Attempting to pause OneDrive..." -ForegroundColor Yellow
try {
    $onedriveProcess = Get-Process -Name "OneDrive.Sync.Service" -ErrorAction SilentlyContinue
    if ($onedriveProcess) {
        Write-Host "  OneDrive sync service is running. Please pause it manually:" -ForegroundColor Yellow
        Write-Host "  1. Right-click OneDrive icon in system tray" -ForegroundColor White
        Write-Host "  2. Click 'Pause syncing' -> '2 hours'" -ForegroundColor White
        Write-Host ""
        Write-Host "  Press Enter after pausing OneDrive..." -ForegroundColor Yellow
        Read-Host
    }
} catch {
    Write-Host "  Could not check OneDrive status" -ForegroundColor Yellow
}

# Step 2: Remove corrupted .git folder
Write-Host "Step 2: Removing corrupted .git folder..." -ForegroundColor Yellow
$maxRetries = 5
$retryCount = 0
$success = $false

while ($retryCount -lt $maxRetries -and -not $success) {
    try {
        if (Test-Path .git) {
            # Try to remove lock files first
            $lockFiles = @(".git\config.lock", ".git\index.lock", ".git\HEAD.lock")
            foreach ($lockFile in $lockFiles) {
                if (Test-Path $lockFile) {
                    Remove-Item $lockFile -Force -ErrorAction SilentlyContinue
                }
            }
            
            # Remove .git folder
            Remove-Item -Recurse -Force .git -ErrorAction Stop
            Write-Host "  Successfully removed .git folder" -ForegroundColor Green
            $success = $true
        } else {
            Write-Host "  .git folder doesn't exist" -ForegroundColor Green
            $success = $true
        }
    } catch {
        $retryCount++
        Write-Host "  Attempt $retryCount/$maxRetries failed. Waiting 2 seconds..." -ForegroundColor Yellow
        Start-Sleep -Seconds 2
    }
}

if (-not $success) {
    Write-Host ""
    Write-Host "ERROR: Could not remove .git folder. OneDrive is still locking files." -ForegroundColor Red
    Write-Host ""
    Write-Host "Please try:" -ForegroundColor Yellow
    Write-Host "  1. Pause OneDrive syncing (system tray -> Pause syncing)" -ForegroundColor White
    Write-Host "  2. Close all File Explorer windows" -ForegroundColor White
    Write-Host "  3. Wait 10 seconds" -ForegroundColor White
    Write-Host "  4. Run this script again" -ForegroundColor White
    exit 1
}

# Step 3: Initialize Git
Write-Host ""
Write-Host "Step 3: Initializing Git repository..." -ForegroundColor Yellow
Start-Sleep -Seconds 1
git init

if ($LASTEXITCODE -eq 0) {
    Write-Host "  Git repository initialized successfully!" -ForegroundColor Green
    
    # Step 4: Add files
    Write-Host ""
    Write-Host "Step 4: Staging all files..." -ForegroundColor Yellow
    git add .
    
    # Step 5: Create initial commit
    Write-Host ""
    Write-Host "Step 5: Creating initial commit..." -ForegroundColor Yellow
    git commit -m "Initial commit: ThunderEdge Valorant KPR Betting Analysis Tool"
    
    Write-Host ""
    Write-Host "=" * 60 -ForegroundColor Green
    Write-Host "SUCCESS! Git repository is ready." -ForegroundColor Green
    Write-Host "=" * 60 -ForegroundColor Green
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Cyan
    Write-Host "  1. Add remote: git remote add origin https://github.com/jxc2008/thunderedge.git" -ForegroundColor White
    Write-Host "  2. Push: git push -u origin main" -ForegroundColor White
} else {
    Write-Host ""
    Write-Host "ERROR: Could not initialize Git repository." -ForegroundColor Red
    exit 1
}
