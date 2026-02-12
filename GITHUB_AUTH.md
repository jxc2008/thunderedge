# GitHub Authentication Guide

## Problem
You're signed in as `d-huang05` but need to push to `jxc2008/thunderedge`.

## Solution: Use Personal Access Token

GitHub no longer accepts passwords for HTTPS. You need to create a Personal Access Token (PAT).

### Step 1: Create Personal Access Token

1. **Go to GitHub Settings**:
   - Visit: https://github.com/settings/tokens
   - Or: GitHub → Your Profile → Settings → Developer settings → Personal access tokens → Tokens (classic)

2. **Generate New Token**:
   - Click **"Generate new token"** → **"Generate new token (classic)"**
   - **Note**: Name it something like "ThunderEdge Project"
   - **Expiration**: Choose your preference (90 days, 1 year, or no expiration)
   - **Scopes**: Check these boxes:
     - ✅ `repo` (Full control of private repositories)
     - ✅ `workflow` (if you plan to use GitHub Actions)

3. **Generate and Copy Token**:
   - Click **"Generate token"**
   - **⚠️ IMPORTANT**: Copy the token immediately - you won't be able to see it again!
   - It will look like: `ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`

### Step 2: Use Token to Push

When you run `git push`, Git will prompt for credentials:

```powershell
git push -u origin main
```

**When prompted:**
- **Username**: `jxc2008`
- **Password**: Paste your Personal Access Token (NOT your GitHub password)

### Alternative: Store Token in URL (Temporary)

If you want to avoid entering it each time, you can temporarily include it in the URL:

```powershell
git remote set-url origin https://jxc2008:YOUR_TOKEN_HERE@github.com/jxc2008/thunderedge.git
git push -u origin main
```

**⚠️ Security Note**: This stores the token in plain text in `.git/config`. Only use this if you're comfortable with that, or remove it after pushing.

### Alternative: Use SSH (Recommended for Long-term)

For better security, consider using SSH keys:

1. **Generate SSH Key** (if you don't have one):
   ```powershell
   ssh-keygen -t ed25519 -C "jxc2008@nyu.edu"
   ```

2. **Add SSH Key to GitHub**:
   - Copy your public key: `cat ~/.ssh/id_ed25519.pub`
   - Go to: https://github.com/settings/keys
   - Click "New SSH key"
   - Paste your public key

3. **Change Remote to SSH**:
   ```powershell
   git remote set-url origin git@github.com:jxc2008/thunderedge.git
   git push -u origin main
   ```

## Quick Fix (Right Now)

**Option 1: Use Personal Access Token (Easiest)**
1. Create token at: https://github.com/settings/tokens
2. Run: `git push -u origin main`
3. When prompted, username: `jxc2008`, password: paste your token

**Option 2: Use GitHub CLI (If Installed)**
```powershell
gh auth login
git push -u origin main
```

## Verify Authentication

After pushing successfully, verify with:
```powershell
git remote -v
```

You should see your repository URL pointing to `jxc2008/thunderedge.git`.
