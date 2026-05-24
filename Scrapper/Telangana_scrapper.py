import os
import requests
import json
import re
import time
import hashlib
import random
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
import psycopg2
from psycopg2 import extras
from dateutil import parser as dateutil_parser

# Load database credentials from .env
load_dotenv()

BASE_URL = "https://tender.telangana.gov.in"
HOME_URL = f"{BASE_URL}/TenderDetailsHome.html#"
API_URL  = f"{BASE_URL}/TenderDetailsHomeJson.html"

SOURCE_PORTAL  = "telangana_eprocurement"
BACKFILL_DAYS  = 1
PAGE_SIZE      = 20
MAX_PAGES      = 150    # ceiling to prevent infinite loops
PAGE_DELAY     = 1.5

USER_AGENTS = [
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0",
]

# ── Helpers ────────────────────────────────────────────────────────────────────

def make_id(source_portal: str, tender_ref_no: str) -> str:
    """Generates a deterministic SHA-256 ID."""
    raw = f"{source_portal}::{tender_ref_no}"
    return hashlib.sha256(raw.encode()).hexdigest()

def normalize_date(date_str):
    """Parses DD/MM/YYYY formats into timezone-aware UTC datetime."""
    if not date_str or str(date_str).strip() in ["-", "", "None"]:
        return None
    try:
        dt = dateutil_parser.parse(str(date_str).strip(), dayfirst=True)
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    except Exception:
        return None

def normalize_value(val_str):
    """Strips currency symbols to extract pure numeric estimated value."""
    if not val_str:
        return None
    cleaned = re.sub(r"[^\d.]", "", str(val_str))
    try:
        return float(cleaned) if cleaned else None
    except ValueError:
        return None

def derive_status(deadline_dt):
    """Derives standard schema status based on the closing deadline."""
    if not deadline_dt:
        return "unknown"
    return "open" if deadline_dt > datetime.now(tz=timezone.utc) else "closed"

def extract_buyer_name(org_chain):
    """Extracts the most specific buyer name (the last segment) from the org chain."""
    if not org_chain:
        return None
    parts = [p.strip() for p in re.split(r">>|-(?!>)|,", org_chain)]
    return parts[-1] if parts else org_chain

def classify_category(raw_category: str) -> str:
    """Standardizes portal categories into the Unified Schema formats."""
    if not raw_category:
        return "unknown"
    c = raw_category.strip().upper()
    mapping = {
        "WORKS":       "works",
        "GOODS":       "goods",
        "SERVICES":    "services",
        "CONSULTANCY": "consultancy",
    }
    return mapping.get(c, "unknown")

# ── Scraper class ──────────────────────────────────────────────────────────────

class TelanganaTenderScraper:

    def __init__(self):
        self.session = requests.Session()
        self._bootstrap()

    def _bootstrap(self):
        """Initializes session cookies by hitting the portal homepage first."""
        print("[*] Bootstrapping session...")
        for attempt in range(3):
            self.session.headers.update({"User-Agent": random.choice(USER_AGENTS)})
            try:
                resp = self.session.get(HOME_URL, timeout=45)
                print(f"    Homepage: HTTP {resp.status_code}")
                return  # success — cookies set
            except Exception as e:
                delay = 3.0 * (2 ** attempt) + random.uniform(0, 1)
                print(f"    [!] Bootstrap attempt {attempt + 1}/3 failed: {e}")
                if attempt < 2:
                    print(f"        Retrying in {delay:.1f}s...")
                    time.sleep(delay)
                else:
                    print("    [!] Bootstrap failed after 3 attempts — proceeding without session cookies.")

    def _build_params(self, start: int, length: int, echo: int) -> dict:
        return {
            "nTenderID": "", "nDepartmentID": "0", "subDeptId": "",
            "ddlDistrict": "", "ddlMandal": "", "biddingType": "",
            "sProcurementType": "", "mECVValue1": "", "mECVValue2": "",
            "dtBidClosingselect": "", "dtBidClosing1": "", "dtBidClosing2": "",
            "dtTenderOpening1": "", "dtTenderOpening2": "",
            "hdnSearch4": "", "hdnSearch": "", "hdncorrigendumsDetails": "",
            "hdncorrigendumsDetails1": "", "hdnnoSearch": "",
            "hdncorrigendumsDetails2": "", "hdnPreviousPage": "",
            "hdnIndentID": "", "hdnTenderCategory": "", "hdnProcurementID": "",
            "hdnType": "current", "hdnPreviousPge": "TenderDetailsHome.html",
            "hdnadvsearch": "", "hdnFromStatus": "", "typeOfWorkFromConsolidation": "",
            "popUPRequestParameter": "", "selectedCircleDivison": "",
            "selectedDepartmentID": "", "selectedProcurementType": "",
            "selectedTypeofWork": "", "aid": "",
            "hdnEncryptNames": "hdnEncryptNames",
            "hdnEncryptValues": "hdnEncryptValues",
            "sEcho": str(echo), "iColumns": "10", "sColumns": ",,,,,,,,,",
            "iDisplayStart": str(start),        
            "iDisplayLength": str(length),
            "mDataProp_0": "0", "bSortable_0": "true",
            "mDataProp_1": "1", "bSortable_1": "true",
            "mDataProp_2": "2", "bSortable_2": "true",
            "mDataProp_3": "3", "bSortable_3": "true",
            "mDataProp_4": "4", "bSortable_4": "true",
            "mDataProp_5": "5", "bSortable_5": "true",
            "mDataProp_6": "6", "bSortable_6": "true",
            "mDataProp_7": "7", "bSortable_7": "true",
            "mDataProp_8": "8", "bSortable_8": "true",
            "mDataProp_9": "9", "bSortable_9": "false",
            "iSortCol_0": "6",          # CRITICAL: Sorts by published_date column
            "sSortDir_0": "desc",       # CRITICAL: Newest first
            "iSortingCols": "1",
            "_": str(int(time.time() * 1000))
        }

    def _fetch_page(self, start: int, length: int, echo: int) -> dict:
        params  = self._build_params(start, length, echo)
        headers = {
            "X-Requested-With": "XMLHttpRequest",
            "Referer": HOME_URL,
            "Accept":  "application/json, text/plain, */*",
        }

        for attempt in range(5):
            self.session.headers.update({"User-Agent": random.choice(USER_AGENTS)})
            try:
                resp = self.session.get(API_URL, params=params,
                                        headers=headers, timeout=30)
                if resp.status_code == 200:
                    break
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
        else:
            raise RuntimeError("Max retries reached — server blocking or network issue.")

        raw = resp.text.strip()
        if not raw:
            raise RuntimeError("Empty response from API.")

        try:
            return resp.json()
        except Exception as e:
            with open("telangana_debug.txt", "w", encoding="utf-8") as f:
                f.write(resp.text)
            raise RuntimeError(f"JSON parse failed: {e} — saved to telangana_debug.txt")

    def _extract_ids(self, html: str) -> dict:
        match = re.search(r"viewBtn\((\d+),(\d+),(\d+)\)", html or "")
        if not match:
            return {}
        return {
            "work_id":          match.group(1),
            "procurement_type": match.group(2),
            "tender_id":        match.group(3),
        }
    
    def _parse_row(self, row: list) -> dict:
        ids = self._extract_ids(row[-1])
        return {
            "department":     row[0],
            "tender_number":  row[1],
            "nit_number":     row[2],
            "category":       row[3],
            "title":          row[4],
            "tender_value":   row[5],
            "published_date": row[6],
            "closing_date":   row[7],
            "ids":            ids,
        }

    # ── Main scrape loop ───────────────────────────────────────────────────────

    def scrape(self) -> list[dict]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=BACKFILL_DAYS)

        print(f"\n{'='*60}")
        print(f"  Telangana eProcurement Scraper — {BACKFILL_DAYS}-day backfill")
        print(f"  Cutoff : {cutoff.strftime('%Y-%m-%d %H:%M UTC')}")
        print(f"{'='*60}\n")

        results       = []
        total_scraped = 0
        reached_cutoff = False

        for page_num in range(MAX_PAGES):
            if reached_cutoff:
                break

            start = page_num * PAGE_SIZE
            echo  = page_num + 1

            print(f"[*] Page {page_num + 1} | offset {start}–{start + PAGE_SIZE - 1}")

            try:
                data = self._fetch_page(start=start, length=PAGE_SIZE, echo=echo)
            except RuntimeError as e:
                print(f"    [-] Fetch failed: {e} — stopping.")
                break

            rows = data.get("aaData", [])
            if not rows:
                print(f"    [✓] Empty page — end of results.")
                break

            print(f"    [+] {len(rows)} rows returned.")
            page_valid = 0

            for row in rows:
                try:
                    raw = self._parse_row(row)
                except Exception as e:
                    print(f"    [!] Row parse error: {e}")
                    continue

                pub_dt = normalize_date(raw["published_date"])

                # ── Chronological Cutoff Check ─────────────────────────────
                if pub_dt is not None and pub_dt < cutoff:
                    print(f"    [✓] Hit cutoff at row {page_valid + 1} "
                          f"(published {pub_dt.strftime('%Y-%m-%d')}) — stopping.")
                    reached_cutoff = True
                    break

                tender_ref_no = str(raw.get("tender_number") or "").strip()
                if not tender_ref_no:
                    continue

                deadline_dt     = normalize_date(raw["closing_date"])
                ids             = raw.get("ids") or {}
                buyer_org_chain = raw.get("department", "")

                results.append({
                    "id":              make_id(SOURCE_PORTAL, tender_ref_no),
                    "tender_ref_no":   tender_ref_no,
                    "nit_number":      raw.get("nit_number"),
                    "source_portal":   SOURCE_PORTAL,
                    "source_url":      f"{HOME_URL}tender_number={tender_ref_no}",
                    "title":           raw.get("title"),
                    "category":        classify_category(raw.get("category")),
                    "buyer_name":      extract_buyer_name(buyer_org_chain),
                    "buyer_org_chain": buyer_org_chain,
                    "state":           "Telangana",
                    "location":        None,
                    "value":           normalize_value(raw.get("tender_value")),
                    "currency":        "INR",
                    "published_at":    pub_dt.isoformat() if pub_dt else None,
                    "deadline_at":     deadline_dt.isoformat() if deadline_dt else None,
                    "opening_at":      None,
                    "status":          derive_status(deadline_dt),
                    "corrigendum":     False,
                    "detail_scraped":  False,
                    "scraped_at":      datetime.now(tz=timezone.utc).isoformat(),
                    "portal_metadata": json.dumps(ids) if ids else "{}",
                })

                page_valid    += 1
                total_scraped += 1

            print(f"    [→] Collected this page: {page_valid}")
            time.sleep(PAGE_DELAY)

        print(f"\n[✓] Scrape complete — {total_scraped} records within {BACKFILL_DAYS}-day window")
        return results


# ── DB upsert ──────────────────────────────────────────────────────────────────

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
        status          = EXCLUDED.status,
        deadline_at     = EXCLUDED.deadline_at,
        value           = EXCLUDED.value,
        corrigendum     = EXCLUDED.corrigendum,
        scraped_at      = EXCLUDED.scraped_at
"""


def upsert(records: list[dict]):
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("[!] DATABASE_URL not set — skipping DB insert.")
        return

    # ── Python-Level Deduplication Fix ──
    # This dictionary automatically overwrites duplicate IDs, leaving only the freshest unique row
    unique_records = {r["id"]: r for r in records}
    deduped_list = list(unique_records.values())
    
    duplicates_removed = len(records) - len(deduped_list)
    if duplicates_removed > 0:
        print(f"[*] Cleaned up {duplicates_removed} duplicate rows from the scraped batch before DB insertion.")

    print("\n[*] Connecting to PostgreSQL...")
    conn   = psycopg2.connect(db_url)
    cursor = conn.cursor()

    try:
        # Pass the deduped_list to PostgreSQL instead of the raw records
        values = [tuple(r.get(col) for col in COLUMNS) for r in deduped_list]
        extras.execute_values(cursor, INSERT_SQL, values, page_size=100)
        conn.commit()
        print(f"[✓] {len(deduped_list)} unique records upserted.")
    except Exception as e:
        conn.rollback()
        print(f"[-] DB insert failed: {e}")
        raise
    finally:
        cursor.close()
        conn.close()

# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    scraper = TelanganaTenderScraper()
    tenders = scraper.scrape()

    if not tenders:
        print("[✗] No valid records found. Exiting.")
        exit()

    upsert(tenders)