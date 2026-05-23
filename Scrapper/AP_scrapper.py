import os
import requests
import json
import re
import time
import base64
import hashlib
import random
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
import psycopg2
from psycopg2 import extras
from dateutil import parser as dateutil_parser

load_dotenv()

BASE_URL = "https://tender.apeprocurement.gov.in/"
HOME_URL = f"{BASE_URL}/TenderDetailsHome.html#"
API_URL  = f"{BASE_URL}/TenderDetailsHomeJson.html"

SOURCE_PORTAL  = "ap_eprocurement"
BACKFILL_DAYS  = 1
PAGE_SIZE      = 20
MAX_PAGES      = 150    # hard ceiling — 150 × 20 = 3000 records max
PAGE_DELAY     = 1.5

USER_AGENTS = [
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0",
]

# ── Helpers ────────────────────────────────────────────────────────────────────

def make_id(source_portal: str, tender_ref_no: str) -> str:
    raw = f"{source_portal}::{tender_ref_no}"
    return hashlib.sha256(raw.encode()).hexdigest()

def normalize_date(date_str):
    if not date_str or str(date_str).strip() in ["-", "", "None"]:
        return None
    try:
        dt = dateutil_parser.parse(str(date_str).strip(), dayfirst=True)
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    except Exception:
        return None

def normalize_value(val_str):
    if not val_str:
        return None
    cleaned = re.sub(r"[^\d.]", "", str(val_str))
    try:
        return float(cleaned) if cleaned else None
    except ValueError:
        return None

def derive_status(deadline_dt):
    """
    AP portal doesn't give explicit status — derive from deadline.
    Returns unified schema values: open | closed
    """
    if not deadline_dt:
        return "unknown"
    return "open" if deadline_dt > datetime.now(tz=timezone.utc) else "closed"

def extract_buyer_name(org_chain):
    """Last segment of org chain is the most specific buyer name."""
    if not org_chain:
        return None
    parts = [p.strip() for p in re.split(r">>|-(?!>)|,", org_chain)]
    return parts[-1] if parts else org_chain

def classify_category(raw_category: str) -> str:
    """Normalise AP portal category text → unified schema values."""
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

class APTenderScraper:

    def __init__(self):
        self.session = requests.Session()
        self._bootstrap()

    def _bootstrap(self):
        """Initialise session cookies by hitting the homepage first."""
        print("[*] Bootstrapping session...")
        self.session.headers.update({"User-Agent": random.choice(USER_AGENTS)})
        resp = self.session.get(HOME_URL, timeout=30)
        print(f"    Homepage: HTTP {resp.status_code}")
        print(f"    Cookies : {dict(self.session.cookies)}")

    def _build_params(self, start: int, length: int, echo: int) -> dict:
        return {
            "nTenderID": "", "nDepartmentID": "", "subDeptId": "",
            "ddlDistrict": "", "ddlMandal": "", "biddingType": "",
            "sProcurementType": "", "mECVValue1": "", "mECVValue2": "",
            "dtBidClosingselect": "", "dtBidClosing1": "", "dtBidClosing2": "",
            "dtTenderOpening1": "", "dtTenderOpening2": "",
            "hdnSearch4": "", "hdnSearch": "", "hdncorrigendumsDetails": "",
            "hdncorrigendumsDetails1": "", "hdnnoSearch": "",
            "hdncorrigendumsDetails2": "", "hdnadvsearch": "",
            "hdnPreviousPage": "", "hdnIndentID": "", "hdnTenderCategory": "",
            "hdnProcurementID": "", "hdnType": "current",
            "hdnPreviousPge": "TenderDetailsHome.html",
            "hdnFromStatus": "", "typeOfWorkFromConsolidation": "",
            "popUPRequestParameter": "", "selectedCircleDivison": "",
            "selectedDepartmentID": "", "selectedProcurementType": "",
            "selectedTypeofWork": "", "aid": "",
            "hdnEncryptNames": "hdnEncryptNames",
            "hdnEncryptValues": "hdnEncryptValues",
            "sEcho": str(echo), "iColumns": "9", "sColumns": ",,,,,,,,",
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
            "mDataProp_8": "8", "bSortable_8": "false",
            "iSortCol_0": "6", "sSortDir_0": "desc",   # FIXED: Now correctly sorts by published_date desc
            "iSortingCols": "1",
            "_": str(int(time.time() * 1000))
        }

    def _fetch_page(self, start: int, length: int, echo: int) -> dict:
        params  = self._build_params(start, length, echo)
        headers = {
            "X-Requested-With": "XMLHttpRequest",
            "Referer": HOME_URL,
            "Accept":  "*/*",
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

        # AP portal returns Base64-encoded JSON
        try:
            decoded = base64.b64decode(raw).decode("utf-8")
        except Exception as e:
            raise RuntimeError(f"Base64 decode failed: {e}")

        try:
            return json.loads(decoded)
        except Exception as e:
            with open("ap_debug.txt", "w", encoding="utf-8") as f:
                f.write(decoded)
            raise RuntimeError(f"JSON parse failed: {e} — saved to ap_debug.txt")

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
        print(f"    [DEBUG] raw dates → published: '{row[6]}' | closing: '{row[7]}'")
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
        print(f"  AP eProcurement Scraper — {BACKFILL_DAYS}-day backfill")
        print(f"  Cutoff : {cutoff.strftime('%Y-%m-%d %H:%M UTC')}")
        print(f"  Max    : {MAX_PAGES} pages × {PAGE_SIZE} = {MAX_PAGES*PAGE_SIZE} records")
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

                # ── Cutoff check ───────────────────────────────────────────
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
                    "state":           "AP",
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

    # ── Deduplication Fix ──
    # Dictionary comprehension automatically overwrites duplicates, leaving only unique IDs.
    unique_records = {r["id"]: r for r in records}
    deduped_list = list(unique_records.values())
    
    duplicates_removed = len(records) - len(deduped_list)
    if duplicates_removed > 0:
        print(f"[*] Cleaned up {duplicates_removed} duplicate rows from the scraped batch.")

    print("\n[*] Connecting to PostgreSQL...")
    conn   = psycopg2.connect(db_url)
    cursor = conn.cursor()

    try:
        # Pass the deduped_list instead of the raw records
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
    scraper = APTenderScraper()
    tenders = scraper.scrape()

    if not tenders:
        print("[✗] No valid records found. Exiting.")
        exit()

    upsert(tenders)