# Technology Stack

**Analysis Date:** 2026-03-07

## Languages

**Primary:**
- TypeScript ^5 - Frontend (Next.js app, components, lib)
- Python 3.x - Backend (Flask API, scrapers, data processing)

**Secondary:**
- JavaScript - Config files (`next.config.js`, `postcss.config.mjs`, `tailwind.config.js`)
- SQL - SQLite queries embedded in `backend/database.py`

## Runtime

**Environment:**
- Node.js (version not pinned; no `.nvmrc` present)
- Python 3.x (version not pinned; no `.python-version` present)

**Package Manager:**
- npm - Frontend (`package.json`)
- pip - Backend (`requirements.txt`)
- Lockfile: `package-lock.json` expected for npm; no `Pipfile.lock` or `poetry.lock`

## Frameworks

**Core:**
- Next.js ^15.2.9 - Frontend framework (App Router, `app/` directory)
- React 19.2.0 - UI library
- Flask 3.0.0 - Python backend API (`backend/api.py`)
- Flask-CORS 4.0.0 - Cross-origin request handling

**Build/Dev:**
- Tailwind CSS ^4.1.9 - Utility-first CSS (`@tailwindcss/postcss` plugin)
- PostCSS ^8.5 - CSS processing (`postcss.config.mjs`)
- Autoprefixer ^10.4.20 - CSS vendor prefixes
- TypeScript ^5 - Type checking (strict mode OFF in `tsconfig.json`)

**No test framework detected** - No jest, vitest, or other test runner configured.

## Key Dependencies

**Critical (Frontend):**
- `next` ^15.2.9 - App framework with API proxy rewrites to Flask
- `react` / `react-dom` 19.2.0 - UI rendering
- `recharts` 2.15.4 - Data visualization charts (kill distributions, stats)
- `zod` 3.25.76 - Schema validation
- `react-hook-form` ^7.60.0 - Form management
- `@hookform/resolvers` ^3.10.0 - Form validation resolvers
- `sonner` ^1.7.4 - Toast notifications
- `next-themes` ^0.4.6 - Dark/light theme support

**UI Components (Radix UI primitives):**
- Full Radix UI suite installed: accordion, alert-dialog, avatar, checkbox, collapsible, context-menu, dialog, dropdown-menu, hover-card, label, menubar, navigation-menu, popover, progress, radio-group, scroll-area, select, separator, slider, slot, switch, tabs, toast, toggle, toggle-group, tooltip
- `class-variance-authority` ^0.7.1 - Component variant styling (shadcn/ui pattern)
- `clsx` ^2.1.1 - Conditional classnames
- `tailwind-merge` ^3.3.1 - Tailwind class deduplication
- `cmdk` 1.0.4 - Command palette
- `lucide-react` ^0.454.0 - Icon library
- `vaul` ^1.1.2 - Drawer component
- `react-resizable-panels` ^2.1.7 - Resizable panel layouts
- `embla-carousel-react` 8.5.1 - Carousel
- `react-day-picker` 9.8.0 - Date picker
- `input-otp` 1.4.1 - OTP input
- `tw-animate-css` 1.3.3 - Tailwind animation utilities
- `tailwindcss-animate` ^1.0.7 - Animation plugin

**Analytics:**
- `@vercel/analytics` 1.3.1 - Vercel web analytics

**Utility:**
- `date-fns` 4.1.0 - Date formatting/manipulation

**Critical (Backend):**
- `numpy` 1.26.2 - Numerical computation (kill distribution fitting)
- `scipy` 1.11.4 - Statistical distributions (Poisson, Negative Binomial)
- `requests` 2.31.0 - HTTP client for web scraping
- `beautifulsoup4` 4.12.2 - HTML parsing for scrapers
- `google-generativeai` >=0.8.0 - Gemini vision API for PrizePicks screenshot parsing
- `python-dotenv` 1.0.0 - Environment variable loading
- `gunicorn` 21.2.0 - Production WSGI server

## Configuration

**Environment:**
- `.env` file present - contains environment configuration (GOOGLE_API_KEY for Gemini)
- `BACKEND_URL` env var - Flask backend URL (default: `http://localhost:5000`)
- `NEXT_PUBLIC_BACKEND_URL` env var - Client-side backend URL
- `DATABASE_PATH` env var - Override SQLite database location
- Proxy env vars force-disabled in `config.py` for Windows compatibility

**Build:**
- `next.config.js` - Webpack alias `@` to project root; API rewrites `/api/*` to Flask
- `tsconfig.json` - Target ES2017, module ESNext, path alias `@/*` to root
- `postcss.config.mjs` - `@tailwindcss/postcss` + `autoprefixer`
- `tailwind.config.js` - Content paths: `app/**`, `components/**`

**TypeScript:**
- Strict mode: OFF (`"strict": false`)
- No emit mode: ON (type checking only, Next.js handles compilation)
- Incremental compilation: ON

## Platform Requirements

**Development:**
- Node.js + npm for frontend
- Python 3.x + pip for backend
- Both servers run simultaneously: Next.js on port 3000, Flask on port 5000
- Next.js proxies `/api/*` requests to Flask backend
- SQLite database at `data/valorant_stats.db`

**Production:**
- Gunicorn for Flask (configured in `requirements.txt`)
- Vercel Analytics SDK present (`@vercel/analytics`) suggesting Vercel deployment target for frontend
- No Docker or container configuration detected

**Known Build Issue:**
- `npm run build` fails on prerender of `/challengers` and `/moneylines` routes
- Workaround: use `npx tsc --noEmit` for type checking instead of full build

---

*Stack analysis: 2026-03-07*
