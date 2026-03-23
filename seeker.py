"""
seeker.py — SEEK AU jobs market scraper (Playwright direct)
Pulls weekly snapshots from SEEK and stores in SQLite for trend analysis.
"""

import re
import sys
import json
import asyncio
import sqlite3
from datetime import datetime, date
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── Config ────────────────────────────────────────────────────────────────────
DB_PATH = "seek_data.db"

STATES = {
    "NSW": "New+South+Wales+NSW",
    "VIC": "Victoria+VIC",
    "QLD": "Queensland+QLD",
    "WA":  "Western+Australia+WA",
    "SA":  "South+Australia+SA",
    "TAS": "Tasmania+TAS",
    "ACT": "Australian+Capital+Territory+ACT",
    "NT":  "Northern+Territory+NT",
}

# ── Database ──────────────────────────────────────────────────────────────────
def init_db():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS snapshots (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_date  TEXT    NOT NULL,
            run_id         TEXT,
            total_listings INTEGER,
            created_at     TEXT    DEFAULT (datetime('now'))
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS listings (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_date  TEXT    NOT NULL,
            job_id         TEXT,
            title          TEXT,
            company        TEXT,
            location       TEXT,
            state          TEXT,
            category       TEXT,
            subcategory    TEXT,
            salary_min     REAL,
            salary_max     REAL,
            salary_type    TEXT,
            work_type      TEXT,
            posted_date    TEXT,
            days_on_market INTEGER,
            url            TEXT,
            UNIQUE(snapshot_date, job_id)
        )
    """)
    con.commit()
    con.close()
    print("Database ready:", DB_PATH)


# ── Parse ─────────────────────────────────────────────────────────────────────
def parse_salary(job):
    sal = job.get("salary") or job.get("salaryLabel") or ""
    if not sal:
        return None, None, ""
    nums = [int(n.replace(",", "")) for n in re.findall(r"[\d,]+", sal)
            if int(n.replace(",", "")) > 999]
    sal_min  = nums[0] if nums else None
    sal_max  = nums[1] if len(nums) > 1 else sal_min
    sal_type = "annual" if "year" in sal.lower() else ("hourly" if "hour" in sal.lower() else "")
    return sal_min, sal_max, sal_type


def days_since(date_str):
    if not date_str:
        return None
    try:
        posted = datetime.fromisoformat(date_str.replace("Z", "+00:00")).date()
        return (date.today() - posted).days
    except Exception:
        return None


# ── Store ─────────────────────────────────────────────────────────────────────
def store_listings(state, total_count, jobs):
    today    = date.today().isoformat()
    con      = sqlite3.connect(DB_PATH)
    cur      = con.cursor()
    inserted = 0
    skipped  = 0

    for job in jobs:
        try:
            sal_min, sal_max, sal_type = parse_salary(job)
            adv     = job.get("advertiser") or {}
            company = (adv.get("description") or adv.get("name") or "") if isinstance(adv, dict) else str(adv)
            cls     = job.get("classification") or {}
            cat     = (cls.get("description") or "") if isinstance(cls, dict) else str(cls)
            subcat  = (job.get("subClassification") or {}).get("description") or ""
            posted  = job.get("listingDate") or job.get("postedAt") or ""
            job_id  = str(job.get("id") or job.get("jobId") or "")
            url     = f"https://www.seek.com.au/job/{job_id}" if job_id else ""
            loc     = job.get("location") or job.get("suburb") or ""

            cur.execute("""
                INSERT OR IGNORE INTO listings
                    (snapshot_date, job_id, title, company, location, state,
                     category, subcategory, salary_min, salary_max, salary_type,
                     work_type, posted_date, days_on_market, url)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                today, job_id,
                job.get("title") or "",
                company, loc, state, cat, subcat,
                sal_min, sal_max, sal_type,
                job.get("workType") or job.get("employmentType") or "",
                posted, days_since(posted), url,
            ))
            if cur.rowcount > 0:
                inserted += 1
            else:
                skipped += 1
        except Exception as e:
            print(f"  Row error: {e}")

    cur.execute(
        "INSERT INTO snapshots (snapshot_date, run_id, total_listings) VALUES (?,?,?)",
        (today, f"direct-{state}", total_count),
    )
    con.commit()
    con.close()
    return inserted, skipped


# ── Scrape ────────────────────────────────────────────────────────────────────
async def scrape_state(page, state, slug):
    url = f"https://www.seek.com.au/jobs?where={slug}"
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)

        html = await page.content()

        # Extract embedded Next.js data
        m = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
            html, re.DOTALL,
        )
        if not m:
            # Fallback: try to find totalCount in raw HTML
            tc = re.search(r'"totalCount"\s*:\s*(\d+)', html)
            total = int(tc.group(1)) if tc else 0
            return total, []

        data  = json.loads(m.group(1))
        props = data.get("props", {}).get("pageProps", {})
        total = props.get("totalCount") or 0
        jobs  = props.get("jobResults", props.get("results", []))
        if isinstance(jobs, dict):
            jobs = jobs.get("jobs", jobs.get("data", []))

        return total, jobs or []

    except Exception as e:
        print(f"  Error: {e}")
        return 0, []


async def run_scrape():
    print("=" * 60)
    print(f"  SEEK AU Weekly Scrape -- {date.today()}")
    print("=" * 60)
    init_db()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="en-AU",
            timezone_id="Australia/Sydney",
        )
        page = await context.new_page()
        await Stealth().apply_stealth_async(page)

        # Warm up on homepage
        print("Warming up...")
        await page.goto("https://www.seek.com.au", wait_until="load", timeout=20000)
        await asyncio.sleep(3)

        grand_total = 0
        for state, slug in STATES.items():
            print(f"  {state}...", end="", flush=True)
            total, jobs = await scrape_state(page, state, slug)
            inserted, skipped = store_listings(state, total, jobs)
            print(f" {total:,} jobs | {len(jobs)} scraped | {inserted} stored")
            grand_total += total
            await asyncio.sleep(4)

        await browser.close()

    print(f"\nScrape complete. Total jobs across all states: {grand_total:,}")
    print(f"Database: {DB_PATH}")


if __name__ == "__main__":
    asyncio.run(run_scrape())
