import os
import csv
import time
import requests
import hashlib
import random
import re
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
import psycopg2
from psycopg2 import extras

load_dotenv()

BASE_API_URL = "https://kppp.karnataka.gov.in/supplier-registration-service"
CSV_FILE     = "karnataka_tenders.csv"
SOURCE_PORTAL = "kppp"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
]

CATEGORY_CONFIGS = {
    "GOODS": {
        "endpoint": f"{BASE_API_URL}/v1/api/portal-service/search-eproc-tenders",
        "start_page": 1
    },
    "WORKS": {
        "endpoint": f"{BASE_API_URL}/v1/api/portal-service/works/search-eproc-tenders",
        "start_page": 1
    },
    "SERVICES": {
        "endpoint": f"{BASE_API_URL}/v1/api/portal-service/services/search-eproc-tenders",
        "start_page": 0
    }
}

# ── Helpers ────────────────────────────────────────────────────────────────────

def make_id(source_portal: str, tender_ref_no: str) -> str:
    raw = f"{source_portal}::{tender_ref_no}"
    return hashlib.sha256(raw.encode()).hexdigest()

def normalize_date(date_val):
    if not date_val:
        return None
    if isinstance(date_val, (int, float)):
        return datetime.fromtimestamp(date_val / 1000.0, tz=timezone.utc)
    formats = [
        "%d/%m/%Y %H:%M:%S", "%d-%m-%Y %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%d",
        "%d/%m/%Y %I:%M %p", "%d/%m/%Y",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(str(date_val).strip(), fmt)
            return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
        except ValueError:
            continue
    try:
        from dateutil import parser
        dt = parser.parse(str(date_val))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    except Exception:
        return None

def normalize_date_iso(date_val):
    dt = normalize_date(date_val)
    return dt.isoformat() if dt else None

def normalize_value(val_str):
    if not val_str or str(val_str).strip() in ("---", "", "None"):
        return None
    cleaned = re.sub(r'[^\d.]', '', str(val_str))
    try:
        return float(cleaned) if cleaned else None
    except ValueError:
        return None

def derive_status(status_text, deadline_dt):
    """Normalise portal status text → unified allowed values."""
    if status_text:
        s = status_text.strip().lower()
        if any(k in s for k in ["publish", "active", "open"]):
            return "open"
        if any(k in s for k in ["close", "expired", "finish"]):
            return "closed"
        if "cancel" in s:
            return "cancelled"
        if "award" in s:
            return "awarded"
    # fallback: derive from deadline
    if deadline_dt:
        return "open" if deadline_dt > datetime.now(tz=timezone.utc) else "closed"
    return "unknown"

# ── Fetching ───────────────────────────────────────────────────────────────────

def fetch_tender_page(endpoint, page_num, category_name):
    params  = {"page": page_num, "size": 20, "order-by-tender-publish": "true"}
    payload = {"category": category_name, "status": "PUBLISHED"}

    for attempt in range(5):
        try:
            headers = {
                "User-Agent":   random.choice(USER_AGENTS),
                "Accept":       "application/json, text/plain, */*",
                "Content-Type": "application/json",
                "Origin":       "https://kppp.karnataka.gov.in",
                "Referer":      "https://kppp.karnataka.gov.in/"
            }
            print(f"    [*] Page {page_num} | {category_name} (attempt {attempt + 1})")
            resp = requests.post(endpoint, headers=headers,
                                 params=params, json=payload, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                # API may return list directly or wrapped in a key
                if isinstance(data, list):
                    return data
                if isinstance(data, dict):
                    return (data.get("content")
                            or data.get("data")
                            or data.get("tenders")
                            or [])
                return []
            elif resp.status_code in [403, 429, 500, 502, 503, 504]:
                delay = 2.0 * (2 ** attempt) + random.uniform(0, 1)
                print(f"    [!] HTTP {resp.status_code} — backing off {delay:.1f}s")
                time.sleep(delay)
            else:
                print(f"    [!] Unhandled HTTP {resp.status_code}")
                return None
        except Exception as e:
            delay = 2.0 * (2 ** attempt) + random.uniform(0, 1)
            print(f"    [-] Network error: {e} — retry in {delay:.1f}s")
            time.sleep(delay)

    print("    [-] Max retries reached.")
    return None

# ── DB ─────────────────────────────────────────────────────────────────────────

def get_conn():
    return psycopg2.connect(os.getenv("DATABASE_URL"))

def upsert_batch(cursor, db_records):
    if not db_records:
        return

    insert_query = """
        INSERT INTO tenders (
            id, tender_ref_no, nit_number, source_portal, source_url,
            title, category, buyer_name, buyer_org_chain, state,
            location, value, currency,
            published_at, deadline_at, opening_at,
            status, corrigendum, detail_scraped, scraped_at
        ) VALUES %s
        ON CONFLICT (id) DO UPDATE SET
            status       = EXCLUDED.status,
            corrigendum  = EXCLUDED.corrigendum,
            deadline_at  = EXCLUDED.deadline_at,
            value        = EXCLUDED.value,
            scraped_at   = EXCLUDED.scraped_at
    """

    columns = [
        "id", "tender_ref_no", "nit_number", "source_portal", "source_url",
        "title", "category", "buyer_name", "buyer_org_chain", "state",
        "location", "value", "currency",
        "published_at", "deadline_at", "opening_at",
        "status", "corrigendum", "detail_scraped", "scraped_at"
    ]

    values = [tuple(row[col] for col in columns) for row in db_records]
    extras.execute_values(cursor, insert_query, values, page_size=100)

# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    # 1-day backfill window
    BACKFILL_DAYS  = 1
    cutoff_date    = datetime.now(timezone.utc) - timedelta(days=BACKFILL_DAYS)
    MAX_PAGES      = 100   # hard ceiling per category — prevents infinite loops
    PAGE_DELAY     = 1.5   # seconds between page requests

    print(f"\n{'='*60}")
    print(f"  Karnataka (KPPP) Scraper — 1-day backfill")
    print(f"  Cutoff: {cutoff_date.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*60}\n")

    all_csv_rows  = []
    all_db_records = []

    for category_name, config in CATEGORY_CONFIGS.items():
        print(f"\n── Category: {category_name} ──────────────────────────────")

        page          = config["start_page"]
        reached_cutoff = False
        category_count = 0

        while not reached_cutoff and page < config["start_page"] + MAX_PAGES:
            data_list = fetch_tender_page(config["endpoint"], page, category_name)

            # Empty page = end of results for this category
            if not data_list:
                print(f"    [✓] No more pages for {category_name} at page {page}.")
                break

            print(f"    [+] {len(data_list)} items on page {page}")

            page_had_valid = False

            for item in data_list:
                pub_dt = normalize_date(item.get("publishedDate"))

                # If this tender is older than 30 days, stop paginating
                if pub_dt and pub_dt < cutoff_date:
                    print(f"    [✓] Hit 30-day boundary at page {page}. Stopping {category_name}.")
                    reached_cutoff = True
                    break

                tender_ref_no = str(item.get("tenderNumber") or item.get("id") or "")
                if not tender_ref_no:
                    continue

                page_had_valid = True
                deadline_dt    = normalize_date(item.get("tenderClosureDate"))
                status_text    = item.get("statusText")
                unified_status = derive_status(status_text, deadline_dt)

                # ── CSV row (original format) ──────────────────────────────
                all_csv_rows.append({
                    "Category":              item.get("categoryText", category_name),
                    "Tender ID":             item.get("id"),
                    "Tender Number":         item.get("tenderNumber"),
                    "Tender Title":          item.get("title"),
                    "Department Name":       item.get("deptName"),
                    "Location":              item.get("locationName"),
                    "Published Date":        normalize_date_iso(item.get("publishedDate")),
                    "Closing Date":          normalize_date_iso(item.get("tenderClosureDate")),
                    "Status":                unified_status,
                    "Estimated Value (ECV)": item.get("ecv") or "---"
                })

                # ── DB record (unified schema) ─────────────────────────────
                all_db_records.append({
                    "id":              make_id(SOURCE_PORTAL, tender_ref_no),
                    "tender_ref_no":   tender_ref_no,
                    "nit_number":      item.get("nitNumber"),
                    "source_portal":   SOURCE_PORTAL,
                    "source_url":      f"https://kppp.karnataka.gov.in/#/portal/tender/details/{item.get('id')}",
                    "title":           item.get("title"),
                    "category":        (item.get("categoryText") or category_name).lower(),
                    "buyer_name":      item.get("deptName"),
                    "buyer_org_chain": None,
                    "state":           "KA",
                    "location":        item.get("locationName"),
                    "value":           normalize_value(item.get("ecv")),
                    "currency":        "INR",
                    "published_at":    pub_dt.isoformat() if pub_dt else None,
                    "deadline_at":     normalize_date_iso(item.get("tenderClosureDate")),
                    "opening_at":      normalize_date_iso(item.get("tenderOpeningDate")),
                    "status":          unified_status,
                    "corrigendum":     bool(item.get("corrigendumFlag", False)),
                    "detail_scraped":  False,
                    "scraped_at":      datetime.now(tz=timezone.utc).isoformat(),
                })

                category_count += 1

            # If entire page was beyond cutoff, stop
            if not page_had_valid and not reached_cutoff:
                print(f"    [✓] Full page beyond cutoff. Stopping {category_name}.")
                break

            page      += 1
            time.sleep(PAGE_DELAY)

        print(f"    [✓] {category_name} done — {category_count} tenders collected.")

    # ── Write CSV ──────────────────────────────────────────────────────────────
    if all_csv_rows:
        with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=all_csv_rows[0].keys())
            writer.writeheader()
            writer.writerows(all_csv_rows)
        print(f"\n[✓] CSV saved → {CSV_FILE} ({len(all_csv_rows)} rows)")
    else:
        print("\n[✗] No valid records found in the 30-day window.")
        return

    # ── Upsert to DB ───────────────────────────────────────────────────────────
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("[!] DATABASE_URL not set. Skipping DB insertion.")
        return

    print(f"\n[*] Connecting to PostgreSQL...")
    try:
        conn   = get_conn()
        cursor = conn.cursor()

        upsert_batch(cursor, all_db_records)
        conn.commit()

        print(f"[✓] {len(all_db_records)} records upserted into PostgreSQL.")
        cursor.close()
        conn.close()

    except Exception as e:
        print(f"[-] Database insertion failed: {e}")
        raise

if __name__ == "__main__":
    main()