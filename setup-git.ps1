# Git Setup Script for ThunderEdge Project
# Run this script after pausing OneDrive syncing

Write-Host "Setting up Git repository..." -ForegroundColor Green

# Remove any existing .git folder if it exists
if (Test-Path .git) {
    Write-Host "Removing existing .git folder..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force .git -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
}

# Initialize git repository
Write-Host "Initializing Git repository..." -ForegroundColor Green
git init

# Check if initialization was successful
if ($LASTEXITCODE -eq 0) {
    Write-Host "Git repository initialized successfully!" -ForegroundColor Green
    
    # Add all files
    Write-Host "Staging all files..." -ForegroundColor Green
    git add .
    
    # Create initial commit
    Write-Host "Creating initial commit..." -ForegroundColor Green
    git commit -m "Initial commit: ThunderEdge Valorant KPR Betting Analysis Tool"
    
    Write-Host "`nGit setup complete!" -ForegroundColor Green
    Write-Host "Next steps:" -ForegroundColor Cyan
    Write-Host "1. Create a new repository on GitHub (github.com/new)" -ForegroundColor White
    Write-Host "2. Run: git remote add origin https://github.com/YOUR_USERNAME/thunderedge.git" -ForegroundColor White
    Write-Host "3. Run: git branch -M main" -ForegroundColor White
    Write-Host "4. Run: git push -u origin main" -ForegroundColor White
} else {
    Write-Host "Error: Could not initialize Git repository." -ForegroundColor Red
    Write-Host "Make sure OneDrive syncing is paused for this folder." -ForegroundColor Yellow
}
