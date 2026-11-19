# SG Price & Voucher Monitor (`ShopMonitor`)

A **100% free, zero-server** Singapore e-commerce price & voucher monitoring agent for **Shopee SG**, **Lazada SG**, and **Amazon SG**, powered by GitHub Pages, GitHub Actions, Playwright Stealth, and Telegram.

## Architecture

- **Mobile Web UI (`docs/index.html`)**: Mobile-first single-page dashboard (Tailwind CSS + Vanilla JS) hosted on **GitHub Pages**, optimized for iPhone Safari.
- **Database (`data/watchlist.json`)**: Stores monitored items, SGT timestamps, cookie health, and price history directly in the repo.
- **Scraper Engine (`scraper/`)**: Python + Playwright + `playwright-stealth` configured for Singapore (`en-SG`, `Asia/Singapore`), supporting both Direct URLs and Store + Keyword search, plus optional exported session cookies.
- **Automated & On-Demand Runner (`.github/workflows/sg-price-monitor.yml`)**: Runs automatically every 4 hours via cron AND on demand via the mobile UI's **"Check Now"** button (`workflow_dispatch`).

---

## Step-by-Step Setup Guide

### 1. Enable GitHub Pages (Mobile Web UI)
1. Open your repository on GitHub: `https://github.com/rezavirtual/ShopMonitor`.
2. Go to **Settings** → **Pages**.
3. Under **Build and deployment** → **Source**, select **Deploy from a branch**.
4. Set **Branch** to `main` and **Folder** to `/docs`, then click **Save**.
5. After ~1 minute, your mobile dashboard will be live at:
   `https://rezavirtual.github.io/ShopMonitor/`
   *(Tip: On iPhone Safari, tap **Share** → **Add to Home Screen** for an app-like experience.)*

### 2. Generate a Fine-Grained Personal Access Token (for Mobile UI)
The mobile UI stores this token **only in your iPhone browser's `localStorage`** so it can commit edits to `data/watchlist.json` and trigger **Check Now**.

1. Go to GitHub **Settings** → **Developer settings** → **Personal access tokens** → **Fine-grained tokens** → **Generate new token**.
2. Name it e.g. `ShopMonitor Mobile UI` and set an expiration.
3. Under **Repository access**, select **Only select repositories** → `rezavirtual/ShopMonitor`.
4. Under **Repository permissions**, grant:
   - **Contents**: `Read and write`
   - **Actions**: `Read and write`
5. Click **Generate token** and copy it.
6. Open your GitHub Pages dashboard on iPhone Safari, tap the **Settings (⚙)** icon, paste the token, and tap **Save & Test**.

### 3. Set Up Telegram Alerts (`TELEGRAM_BOT_TOKEN` & `TELEGRAM_CHAT_ID`)
> **Reusing your existing Amazon project Telegram Bot:** For security, GitHub does not allow reading or copying Secret values from another repository automatically. However, you can reuse the **exact same `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`** from your Amazon project!

1. In `ShopMonitor`, go to **Settings** → **Secrets and variables** → **Actions** → **New repository secret**.
2. Add:
   - `TELEGRAM_BOT_TOKEN`: Your bot token (e.g. from `@BotFather` or your Amazon project).
   - `TELEGRAM_CHAT_ID`: Your Telegram user/group chat ID (you can verify it via `@userinfobot` or `https://api.telegram.org/bot<TOKEN>/getUpdates`).

### 4. (Optional) Export Browser Cookies for Logged-In Vouchers
Public checks work out of the box, but adding session cookies lets the scraper see **logged-in prices, claimable shop/platform vouchers, and bundle deals**. If cookies expire, the scraper falls back to public checks and sends a Telegram warning (at most once every 24 hours).

1. Install the **Cookie-Editor** browser extension on Chrome/Edge/Firefox.
2. Log in to **Shopee SG** (`shopee.sg`), **Lazada SG** (`lazada.sg`), and/or **Amazon SG** (`amazon.sg`).
3. On each site, open **Cookie-Editor** → **Export** → **Export as JSON** (copies a JSON array to your clipboard).
4. In `ShopMonitor` → **Settings** → **Secrets and variables** → **Actions**, add any of:
   - `SHOPEE_COOKIES_JSON`
   - `LAZADA_COOKIES_JSON`
   - `AMAZON_COOKIES_JSON`

---

## Local Development & Testing

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
pytest
```
