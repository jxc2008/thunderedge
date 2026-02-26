# PrizePicks Browser Automation Plan (Future)

This document outlines a long-term approach to automatically capture PrizePicks lines when the API is blocked by Cloudflare.

## Concept

Use browser automation (Playwright) to:
1. Launch a real browser
2. Navigate to PrizePicks and optionally log in (with stored credentials)
3. Navigate to the Valorant lines page
4. Take screenshots of the line cards
5. Run OCR on the screenshots (same logic as image upload)
6. Return the ranked leaderboard

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Trigger        │────▶│  Playwright      │────▶│  Screenshot(s)  │
│  (cron / manual)│     │  - Login (opt)   │     │  of line cards   │
└─────────────────┘     │  - Navigate      │     └────────┬────────┘
                        │  - Scroll/capture│              │
                        └──────────────────┘              ▼
                                               ┌─────────────────┐
                                               │  OCR Parser      │
                                               │  (existing)      │
                                               └────────┬────────┘
                                                        │
                                                        ▼
                                               ┌─────────────────┐
                                               │  Rank by Hit %   │
                                               │  (existing)      │
                                               └─────────────────┘
```

## Implementation Outline

### 1. Dependencies
```bash
pip install playwright
playwright install chromium
```

### 2. Script: `scripts/prizepicks_capture.py`

```python
# Pseudocode
from playwright.sync_api import sync_playwright
import os

def capture_prizepicks_screenshot(headless=True):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 ...'  # Real browser UA
        )
        page = context.new_page()
        
        # Optional: login from env vars
        if os.getenv('PRIZEPICKS_EMAIL') and os.getenv('PRIZEPICKS_PASSWORD'):
            page.goto('https://app.prizepicks.com/login')
            page.fill('[name=email]', os.getenv('PRIZEPICKS_EMAIL'))
            page.fill('[name=password]', os.getenv('PRIZEPICKS_PASSWORD'))
            page.click('button[type=submit]')
            page.wait_for_load_state('networkidle')
        
        # Navigate to Valorant / Esports
        page.goto('https://app.prizepicks.com/league/vlr')  # or correct path
        page.wait_for_selector('.projection-card', timeout=15000)
        
        # Scroll to load all cards, then screenshot
        page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
        page.wait_for_timeout(1000)
        
        # Full page or element screenshot
        screenshot_bytes = page.screenshot(full_page=True)
        
        browser.close()
        return screenshot_bytes
```

### 3. Security: Credentials

- **Never** hardcode credentials
- Use environment variables: `PRIZEPICKS_EMAIL`, `PRIZEPICKS_PASSWORD`
- Or use a secrets manager (e.g. `python-dotenv` with `.env` in `.gitignore`)
- Consider running login only when needed (cookie persistence)

### 4. API Integration

Add `GET /api/prizepicks/leaderboard/auto` that:
1. Calls `capture_prizepicks_screenshot()`
2. Passes bytes to `parse_prizepicks_image()`
3. Runs `_build_leaderboard_from_projections()`
4. Returns JSON (same as upload endpoint)

### 5. Scheduling (Optional)

- Cron job: run every 6–12 hours during VCT season
- Or: button in UI to trigger "Auto-capture" (user must have machine with browser)

### 6. Caveats

- **Playwright** needs a display or virtual framebuffer (e.g. `xvfb` on Linux)
- **Login** may trigger 2FA; consider session persistence
- **PrizePicks** may change selectors; script may need updates
- **Rate limiting**: don’t poll too frequently

## Status

- [ ] Add Playwright + capture script
- [ ] Add `/api/prizepicks/leaderboard/auto` endpoint
- [ ] Add "Auto-Capture" button (runs on server)
- [ ] Document env vars for optional login

For now, **Upload Screenshot** provides a manual workaround that avoids automation complexity.
