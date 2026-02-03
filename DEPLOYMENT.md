# Deployment Guide

## Current Database Structure

The project uses **SQLite** which is compatible with deployment, but with some considerations:

### ✅ **Compatible For:**
- **Single-instance deployments** (Railway, Render, DigitalOcean App Platform)
- **Small to medium traffic** applications
- **Development/staging** environments

### ⚠️ **Limitations:**
- **Not ideal for multiple server instances** (unless using shared storage)
- **Ephemeral filesystems** (Heroku) will lose data on restart
- **Better alternatives for production**: PostgreSQL, MySQL

## Deployment Options

### Option 1: Keep SQLite (Current Setup)
**Best for:** Single-instance deployments, small scale

**Platforms that work well:**
- **Railway** - Persistent storage, easy setup
- **Render** - Persistent disk storage
- **DigitalOcean App Platform** - Persistent volumes
- **Fly.io** - Persistent volumes

**Setup:**
1. Push code to GitHub
2. Connect to deployment platform
3. Set environment variable `DATABASE_PATH` if needed (optional)
4. Run database population script after first deploy

### Option 2: Migrate to PostgreSQL (Recommended for Production)
**Best for:** Production, multiple instances, high traffic

**Benefits:**
- Better concurrency
- Works with multiple server instances
- More reliable for production
- Free tiers available (Supabase, Neon, Railway)

**Migration Steps:**
1. Install `psycopg2` or `psycopg2-binary`
2. Update `backend/database.py` to use PostgreSQL connection
3. Update `config.py` to read `DATABASE_URL` from environment
4. Deploy with PostgreSQL addon (Heroku Postgres, Railway Postgres, etc.)

## Quick Deploy Steps

### Railway (Recommended - Easiest)
1. Push to GitHub
2. Go to [railway.app](https://railway.app)
3. New Project → Deploy from GitHub
4. Select repository
5. Railway auto-detects Python and installs dependencies
6. Set start command: `gunicorn backend.api:app --bind 0.0.0.0:$PORT`
7. Deploy!

### Render
1. Push to GitHub
2. Go to [render.com](https://render.com)
3. New → Web Service
4. Connect GitHub repo
5. Build command: `pip install -r requirements.txt`
6. Start command: `gunicorn backend.api:app --bind 0.0.0.0:$PORT`
7. Deploy!

## Database Population

After deployment, you'll need to populate the database:

```bash
# SSH into your deployment or use a one-off command
python scripts/populate_database.py
```

Or create a management command that can be run via the platform's CLI.

## Environment Variables

Optional environment variables:
- `DATABASE_PATH` - Override database file path (default: `data/valorant_stats.db`)
- `FLASK_ENV` - Set to `production` for production mode
- `PORT` - Server port (usually set by platform)

## Important Notes

1. **Database Backup**: SQLite files should be backed up regularly if using persistent storage
2. **Database Size**: Current database can grow large with all VCT data - monitor disk usage
3. **CORS**: Already configured for cross-origin requests
4. **Static Files**: Frontend is served via Flask templates (no separate build step needed)

## Production Checklist

- [ ] Add `.gitignore` (already added)
- [ ] Update `requirements.txt` with production server (gunicorn added)
- [ ] Test database path works in deployment environment
- [ ] Set up database population script/process
- [ ] Configure CORS if needed for your domain
- [ ] Set `FLASK_ENV=production` in environment
- [ ] Consider rate limiting for API endpoints
- [ ] Set up monitoring/logging
