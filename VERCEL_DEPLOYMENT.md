# Vercel Deployment Guide

This guide will help you deploy both the backend (Flask API) and frontend to Vercel.

## Prerequisites

1. ✅ Code pushed to GitHub (see `setup-git.ps1` instructions)
2. ✅ Vercel account (sign up at [vercel.com](https://vercel.com))
3. ✅ GitHub account connected to Vercel

## Project Structure

- **Backend**: Flask API in `backend/api.py`
- **Frontend**: Flask templates in `frontend/templates/`
- **Vercel Entry Point**: `api/index.py` (serverless function wrapper)

## Deployment Steps

### Step 1: Push to GitHub

1. **Pause OneDrive syncing** for the project folder (right-click OneDrive icon → Pause syncing → 2 hours)

2. **Run the setup script**:
   ```powershell
   cd "c:\Users\Joseph Cheng\OneDrive\Desktop\thunderedge"
   .\setup-git.ps1
   ```

3. **Create GitHub repository**:
   - Go to [github.com/new](https://github.com/new)
   - Repository name: `thunderedge`
   - Choose Public or Private
   - **DO NOT** initialize with README, .gitignore, or license (we already have these)
   - Click "Create repository"

4. **Connect and push**:
   ```powershell
   git remote add origin https://github.com/YOUR_USERNAME/thunderedge.git
   git branch -M main
   git push -u origin main
   ```

### Step 2: Deploy to Vercel

1. **Go to Vercel Dashboard**:
   - Visit [vercel.com/dashboard](https://vercel.com/dashboard)
   - Click "Add New..." → "Project"

2. **Import GitHub Repository**:
   - Select your `thunderedge` repository
   - Click "Import"

3. **Configure Project**:
   - **Framework Preset**: Other (or leave as default)
   - **Root Directory**: `./` (root)
   - **Build Command**: Leave empty (Vercel will auto-detect Python)
   - **Output Directory**: Leave empty
   - **Install Command**: `pip install -r requirements.txt`

4. **Environment Variables** (Optional):
   - `DATABASE_PATH`: `/tmp/valorant_stats.db` (for serverless, use `/tmp` directory)
   - `FLASK_ENV`: `production`
   - `PYTHON_VERSION`: `3.11`

5. **Deploy**:
   - Click "Deploy"
   - Wait for build to complete (usually 2-3 minutes)

### Step 3: Post-Deployment Setup

#### Database Initialization

After deployment, you'll need to populate the database. Since Vercel uses serverless functions, the database will be ephemeral (resets on each deployment). Consider:

**Option A: Use External Database (Recommended)**
- Use a free PostgreSQL database (Supabase, Neon, Railway)
- Update `backend/database.py` to use PostgreSQL
- Set `DATABASE_URL` environment variable in Vercel

**Option B: Use Vercel KV or Vercel Postgres**
- Add Vercel Postgres addon in your project settings
- Update database connection code

**Option C: Keep SQLite (Development Only)**
- Database resets on each deployment
- Good for testing, not for production

#### Populate Database

If using SQLite, you can populate it via Vercel CLI:

```bash
# Install Vercel CLI
npm i -g vercel

# Run populate script
vercel dev  # Start local dev environment
python scripts/populate_database.py
```

## Vercel Configuration Files

- **`vercel.json`**: Main Vercel configuration
- **`api/index.py`**: Serverless function entry point for Flask app

## Important Notes

### Serverless Limitations

1. **Cold Starts**: First request may be slow (2-5 seconds)
2. **Function Timeout**: Default 10 seconds (can be increased to 60s in Pro plan)
3. **Database**: SQLite files in `/tmp` are ephemeral (lost on function restart)

### Recommended Changes for Production

1. **Migrate to PostgreSQL**: Better for serverless environments
2. **Add Caching**: Use Vercel KV or Redis for caching scraped data
3. **Rate Limiting**: Add rate limiting to prevent abuse
4. **Error Monitoring**: Set up Sentry or similar for error tracking

## Troubleshooting

### Build Fails
- Check `requirements.txt` has all dependencies
- Verify Python version compatibility
- Check build logs in Vercel dashboard

### Routes Not Working
- Verify `vercel.json` routes configuration
- Check `api/index.py` exports Flask app correctly
- Ensure all routes are defined in `backend/api.py`

### Database Issues
- SQLite may not work well in serverless (use PostgreSQL)
- Check `DATABASE_PATH` environment variable
- Verify database initialization code runs correctly

### CORS Issues
- Already configured in `backend/api.py` with `CORS(app)`
- If issues persist, check allowed origins

## Next Steps

1. ✅ Push code to GitHub
2. ✅ Deploy to Vercel
3. ⬜ Set up external database (PostgreSQL)
4. ⬜ Configure custom domain (optional)
5. ⬜ Set up monitoring and error tracking
6. ⬜ Add rate limiting and security headers

## Support

- Vercel Docs: [vercel.com/docs](https://vercel.com/docs)
- Flask on Vercel: [vercel.com/docs/python](https://vercel.com/docs/python)
- GitHub Issues: Create an issue in your repository
