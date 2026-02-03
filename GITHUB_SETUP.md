# GitHub Setup Guide - Step by Step

Follow these steps to push your project to GitHub.

## ⚠️ Important: OneDrive Issue

Your project is in OneDrive, which can lock Git files. **You must pause OneDrive syncing** before initializing Git.

### How to Pause OneDrive:

1. **Right-click** the OneDrive icon in your system tray (bottom-right corner)
2. Click **"Pause syncing"**
3. Select **"2 hours"** (or longer if needed)
4. **Keep OneDrive paused** until you finish pushing to GitHub

## Step-by-Step Instructions

### Step 1: Initialize Git Repository

**Option A: Use the Setup Script (Recommended)**

1. Open PowerShell in the project directory:
   ```powershell
   cd "c:\Users\Joseph Cheng\OneDrive\Desktop\thunderedge"
   ```

2. Run the setup script:
   ```powershell
   .\setup-git.ps1
   ```

   This will:
   - Remove any existing `.git` folder
   - Initialize a new Git repository
   - Stage all files
   - Create an initial commit

**Option B: Manual Setup**

If the script doesn't work, run these commands manually:

```powershell
# Navigate to project directory
cd "c:\Users\Joseph Cheng\OneDrive\Desktop\thunderedge"

# Remove existing .git folder (if exists)
Remove-Item -Recurse -Force .git -ErrorAction SilentlyContinue

# Initialize Git
git init

# Add all files
git add .

# Create initial commit
git commit -m "Initial commit: ThunderEdge Valorant KPR Betting Analysis Tool"
```

### Step 2: Create GitHub Repository

1. **Go to GitHub**: [github.com/new](https://github.com/new)
2. **Repository name**: `thunderedge` (or your preferred name)
3. **Description** (optional): "Valorant KPR Betting Analysis Tool"
4. **Visibility**: Choose Public or Private
5. **⚠️ IMPORTANT**: 
   - **DO NOT** check "Add a README file"
   - **DO NOT** check "Add .gitignore"
   - **DO NOT** check "Choose a license"
   - (We already have these files)
6. Click **"Create repository"**

### Step 3: Connect Local Repository to GitHub

After creating the repository, GitHub will show you commands. Use these:

```powershell
# Replace YOUR_USERNAME with your actual GitHub username
git remote add origin https://github.com/YOUR_USERNAME/thunderedge.git

# Rename branch to main (if needed)
git branch -M main

# Push to GitHub
git push -u origin main
```

**If you get authentication errors:**

- **Option 1**: Use GitHub CLI (if installed):
  ```powershell
  gh auth login
  git push -u origin main
  ```

- **Option 2**: Use Personal Access Token:
  1. Go to GitHub Settings → Developer settings → Personal access tokens → Tokens (classic)
  2. Generate new token with `repo` scope
  3. When prompted for password, paste the token instead

- **Option 3**: Use SSH (if configured):
  ```powershell
  git remote set-url origin git@github.com:YOUR_USERNAME/thunderedge.git
  git push -u origin main
  ```

### Step 4: Verify Upload

1. Go to your GitHub repository page
2. You should see all your files
3. Check that these files are present:
   - `backend/`
   - `frontend/`
   - `scraper/`
   - `requirements.txt`
   - `vercel.json`
   - `README.md`
   - `.gitignore`

### Step 5: Resume OneDrive (Optional)

After successfully pushing to GitHub, you can resume OneDrive syncing. However, **it's recommended to exclude the `.git` folder** from OneDrive to prevent future issues:

1. Right-click OneDrive icon → Settings
2. Go to "Sync and backup" → "Advanced settings"
3. Add `.git` to exclusion list

## Troubleshooting

### Error: "Permission denied" or "File is locked"

**Solution**: OneDrive is still syncing. Make sure you paused it.

### Error: "fatal: not a git repository"

**Solution**: The `.git` folder is missing or corrupted. Run:
```powershell
Remove-Item -Recurse -Force .git -ErrorAction SilentlyContinue
git init
```

### Error: "Authentication failed" when pushing

**Solutions**:
- Use Personal Access Token instead of password
- Or set up SSH keys
- Or use GitHub CLI: `gh auth login`

### Error: "Repository not found"

**Solution**: 
- Check the repository URL is correct
- Make sure the repository exists on GitHub
- Verify you have access to the repository

## Next Steps

After successfully pushing to GitHub:

1. ✅ **Deploy to Vercel** - See `VERCEL_DEPLOYMENT.md`
2. ✅ **Set up database** - Consider migrating to PostgreSQL
3. ✅ **Configure environment variables** - In Vercel dashboard
4. ✅ **Test deployment** - Verify all routes work

## Quick Command Reference

```powershell
# Check Git status
git status

# See what files are staged
git status --short

# View commit history
git log --oneline

# Add specific file
git add filename.py

# Commit changes
git commit -m "Your commit message"

# Push changes
git push

# Pull latest changes
git pull
```

## Need Help?

- Git Documentation: [git-scm.com/docs](https://git-scm.com/docs)
- GitHub Help: [docs.github.com](https://docs.github.com)
- Vercel Deployment: See `VERCEL_DEPLOYMENT.md`
