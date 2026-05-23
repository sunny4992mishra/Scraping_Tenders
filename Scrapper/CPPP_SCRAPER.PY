import os
import requests
import re
import time
import json
import hashlib
import gc
import random
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
import psycopg2
from psycopg2 import extras
from dateutil import parser as dateutil_parser

load_dotenv()

BASE_URL      = "https://eprocure.gov.in"
API_URL       = "https://eprocure.gov.in/cppp/latestactivetendersnew/cpppdata"
SOURCE_PORTAL = "cppp"
BACKFILL_DAYS = 1        # Cron runs daily — only pull last 24 hours
MAX_PAGES     = 500      # Safety ceiling
PAGE_DELAY    = 1.5

USER_AGENTS = [
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0",
]

# Column order locked here — upsert always builds tuples from this list
COLUMNS = [
    "id", "tender_ref_no", "nit_number", "source_portal", "source_url",
    "title", "category", "buyer_name", "buyer_org_chain", "state",
    "location", "value", "currency", "published_at", "deadline_at",
    "opening_at", "status", "corrigendum", "detail_scraped", "scraped_at",
    "portal_metadata",
]

INSERT_SQL = f"""
    INSERT INTO tenders ({", ".join(COLUMNS)})
    VALUES %s
    ON CONFLICT (id) DO UPDATE SET
        status      = EXCLUDED.status,
        deadline_at = EXCLUDED.deadline_at,
        value       = EXCLUDED.value,
        corrigendum = EXCLUDED.corrigendum,
        scraped_at  = EXCLUDED.scraped_at
"""

# ── Helpers ───────────────────────────────────────────────────────────────────

def make_id(source_portal: str, tender_ref_no: str) -> str:
    return hashlib.sha256(f"{source_portal}::{tender_ref_no}".encode()).hexdigest()

def normalize_date(date_str):
    if not date_str or str(date_str).strip() in ["-", "", "None", "NA"]:
        return None
    try:
        dt = dateutil_parser.parse(str(date_str).strip())
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    except Exception:
        return None

def normalize_value(val_str):
    if not val_str or val_str.strip().upper() in ["NA", "N/A", "-"]:
        return None
    cleaned = re.sub(r"[^\d.]", "", str(val_str))
    try:
        return float(cleaned) if cleaned else None
    except ValueError:
        return None

def extract_buyer_name(org_chain):
    if not org_chain:
        return None
    parts = [p.strip() for p in re.split(r'\|\|', org_chain)]
    return parts[-1] if parts else org_chain

def derive_state(org_chain):
    if not org_chain:
        return "Central"
    states = [
        "Maharashtra", "Tamil Nadu", "Uttar Pradesh", "Kerala",
        "Rajasthan", "West Bengal", "Karnataka", "AP", "Telangana"
    ]
    for state in states:
        if state.lower() in org_chain.lower():
            return state
    return "Central"

def extract_tender_details(td_element):
    """Extracts title, deep-link URL, Reference No, and Tender ID from the title cell."""
    a_tag = td_element.find("a")
    if a_tag:
        title = a_tag.text.strip()
        a_tag.decompose()
    else:
        title = "N/A"

    remaining_text = td_element.text.strip().lstrip("/").strip()

    # Primary pattern: full CPPP format e.g. 2026_MCGM_123456_1
    id_match = re.search(r"(\d{4}_[A-Za-z0-9_]+_\d+_\d+)", remaining_text)
    if id_match:
        tender_id = id_match.group(1).strip()
    else:
        id_match_alt = re.search(r"(\d{4}_[A-Za-z0-9_]+)", remaining_text)
        tender_id = id_match_alt.group(1).strip() if id_match_alt else None

    ref_no = remaining_text.replace("Tender ID :", "").replace(tender_id or "", "").replace("/", "").strip()
    if not ref_no:
        ref_no = title

    source_url = (
        f"https://eprocure.gov.in/eprocure/app?location=FrontEndTendersBySearch"
        f"&page=FrontEndTendersBySearch&service=page&searchData={tender_id}"
        if tender_id else None
    )

    return {
        "title":      title,
        "nit_number": ref_no,
        "tender_id":  tender_id,
        "source_url": source_url,
    }


# ── DB Upsert ─────────────────────────────────────────────────────────────────

def upsert(records: list[dict]):
    """
    Deduplicates and upserts a batch into the tenders table.
    Tuple order is driven by COLUMNS — safe regardless of dict insertion order.
    """
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("[!] DATABASE_URL not set — skipping DB insert.")
        return
    if not records:
        return

    unique  = {r["id"]: r for r in records}
    deduped = list(unique.values())

    if len(records) > len(deduped):
        print(f"[*] Deduped {len(records) - len(deduped)} duplicate(s) before insert.")

    conn   = psycopg2.connect(db_url)
    cursor = conn.cursor()
    try:
        values = [tuple(r.get(col) for col in COLUMNS) for r in deduped]
        extras.execute_values(cursor, INSERT_SQL, values, page_size=100)
        conn.commit()
        print(f"    [✓] {len(deduped)} records upserted.")
    except Exception as e:
        conn.rollback()
        print(f"    [-] DB upsert failed: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


# ── Core Scraper ──────────────────────────────────────────────────────────────

class CPPPScraper:
    def __init__(self):
        self.session = requests.Session()

    def fetch_page(self, page_num):
        for attempt in range(5):
            self.session.headers.update({"User-Agent": random.choice(USER_AGENTS)})
            try:
                resp = self.session.get(API_URL, params={"page": page_num}, timeout=30)
                if resp.status_code == 200:
                    return resp.text
                elif resp.status_code in [403, 429, 500, 502, 503, 504]:
                    delay = 2.0 * (2 ** attempt) + random.uniform(0, 1)
                    print(f"    [!] HTTP {resp.status_code} — backing off {delay:.1f}s")
                    time.sleep(delay)
                else:
                    resp.raise_for_status()
            except Exception as e:
                delay = 2.0 * (2 ** attempt) + random.uniform(0, 1)
                print(f"    [-] Network error: {e} — retry in {delay:.1f}s")
                time.sleep(delay)
        return None

    def scrape(self):
        """
        Scrapes CPPP for tenders published in the last BACKFILL_DAYS day(s).
        Upserts per page to keep memory flat — no large list accumulates.
        Returns total records upserted.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=BACKFILL_DAYS)

        print(f"\n{'='*60}")
        print(f"  CPPP Central Portal Scraper — {BACKFILL_DAYS}-day backfill")
        print(f"  Cutoff : {cutoff.strftime('%Y-%m-%d %H:%M UTC')}")
        print(f"{'='*60}\n")

        total_upserted = 0

        for page_num in range(1, MAX_PAGES + 1):
            print(f"[*] Parsing page {page_num}...")

            html = self.fetch_page(page_num)
            if not html:
                print("[-] Failed to fetch page. Stopping.")
                break

            soup  = BeautifulSoup(html, "html.parser")
            table = soup.find("table", {"id": "table"})

            if not table:
                print("[-] No table found. End of results or blocked.")
                break

            rows = table.find_all("tr")

            # Free soup once we have rows
            del soup

            if len(rows) <= 1:
                print("[✓] Empty page — end of results.")
                break

            page_records  = []
            reached_cutoff = False
            now_utc        = datetime.now(timezone.utc)   # consistent timestamp for this page

            # rows[0] is the header — skip it
            for row in rows[1:]:
                cols = row.find_all("td")
                if len(cols) != 7:
                    continue

                pub_dt = normalize_date(cols[1].text.strip())

                # ── Hard cutoff: CPPP is chronological so first old row = stop everything
                if pub_dt and pub_dt < cutoff:
                    print(f"    [✓] Reached 1-day cutoff at {pub_dt.strftime('%Y-%m-%d %H:%M UTC')}. Stopping.")
                    reached_cutoff = True
                    break

                details = extract_tender_details(cols[4])
                if not details["tender_id"]:
                    print(f"    [!] Skipping row — no Tender ID found: '{cols[4].text.strip()[:60]}...'")
                    continue

                # Pre-compute dates once per row — no double calls
                deadline_dt = normalize_date(cols[2].text.strip())
                opening_dt  = normalize_date(cols[3].text.strip())
                org_chain   = cols[5].text.strip()

                page_records.append({
                    "id":              make_id(SOURCE_PORTAL, details["tender_id"]),
                    "tender_ref_no":   details["tender_id"],
                    "nit_number":      details["nit_number"],
                    "source_portal":   SOURCE_PORTAL,
                    "source_url":      details["source_url"],
                    "title":           details["title"],
                    "category":        "unknown",
                    "buyer_name":      extract_buyer_name(org_chain),
                    "buyer_org_chain": org_chain,
                    "state":           derive_state(org_chain),
                    "location":        None,
                    "value":           normalize_value(cols[6].text.strip()),
                    "currency":        "INR",
                    "published_at":    pub_dt.isoformat()      if pub_dt      else None,
                    "deadline_at":     deadline_dt.isoformat() if deadline_dt else None,
                    "opening_at":      opening_dt.isoformat()  if opening_dt  else None,
                    "status":          "open" if (deadline_dt and deadline_dt > now_utc) else "closed",
                    "corrigendum":     False,
                    "detail_scraped":  False,
                    "scraped_at":      now_utc.isoformat(),
                    "portal_metadata": "{}",
                })

            print(f"    [→] {len(page_records)} valid tender(s) on this page.")

            # Flush this page to DB and free memory before fetching next page
            if page_records:
                upsert(page_records)
                total_upserted += len(page_records)
                del page_records
                gc.collect()

            if reached_cutoff:
                break

            time.sleep(PAGE_DELAY)

        print(f"\n[✓] Scrape complete — {total_upserted} records upserted total.")
        return total_upserted


# ── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    scraper = CPPPScraper()
    total   = scraper.scrape()

    if total == 0:
        print("[✗] No valid records found. Exiting.")