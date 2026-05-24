# 🏛️ Chardi.ai — Indian Government Tender Intelligence

> Real-time aggregation, normalization, and search across 10 Indian government e-procurement portals.

**Live Dashboard → [indian-tenderdashboard.netlify.app](https://indian-tenderdashboard.netlify.app/)**

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Portal Coverage](#portal-coverage)
- [Database Schema](#database-schema)
- [Project Structure](#project-structure)
- [Setup & Installation](#setup--installation)
- [Scraper Schedule](#scraper-schedule)
- [OCR / CAPTCHA Server](#ocr--captcha-server)
- [API Reference](#api-reference)
- [AI Usage Notes](#ai-usage-notes)
- [Tech Stack](#tech-stack)

---

## Overview

Chardi.ai scrapes, normalizes, and serves tender listings from 10 Indian state and central procurement portals into a single unified PostgreSQL schema. A FastAPI backend exposes filtered, paginated, and exportable endpoints consumed by a plain HTML/CSS/JS dashboard.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     FRONTEND (Netlify)                      │
│              HTML + CSS + JS Dashboard                      │
│        indian-tenderdashboard.netlify.app                   │
└────────────────────────┬────────────────────────────────────┘
                         │  REST API calls
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                  BACKEND (Railway)                          │
│              FastAPI  —  main.py                            │
│   /api/tenders   /api/stats   /api/chart/state              │
│   /api/tenders/export   /api/tenders/{id}                   │
└────────────────────────┬────────────────────────────────────┘
                         │  psycopg2
                         ▼
┌─────────────────────────────────────────────────────────────┐
│               DATABASE (Supabase)                           │
│            PostgreSQL — tenders table                       │
│         Unified schema across all portals                   │
└────────────────────────▲────────────────────────────────────┘
                         │  upsert (ON CONFLICT)
┌─────────────────────────────────────────────────────────────┐
│                  SCRAPERS (Railway)                         │
│   ┌──────────────┐  ┌───────────────┐  ┌────────────────┐  │
│   │ CPPP_SCRAPER │  │ AP_scrapper   │  │ kpp_Scrapper   │  │
│   └──────────────┘  └───────────────┘  └────────────────┘  │
│   ┌──────────────────────┐  ┌─────────────────────────────┐ │
│   │ Telangana_scrapper   │  │ unified_Scrapper            │ │
│   └──────────────────────┘  │ (MH, TN, UP, WB, RJ, KL)   │ │
│                              └──────────────┬──────────────┘ │
│   Cron: daily @ 2:00 AM IST                 │ CAPTCHA?       │
└─────────────────────────────────────────────│───────────────┘
                                              ▼
                         ┌────────────────────────────────┐
                         │   OCR Server (Railway)         │
                         │   FastAPI + ddddocr            │
                         │   POST /v1/decode-captcha      │
                         └────────────────────────────────┘
```

**Data flow:** Scrapers run nightly, fetch portal pages (HTML/JSON/API), normalize fields into the unified schema, and upsert directly into Supabase PostgreSQL. The FastAPI backend reads from the same DB and serves the dashboard.

---

## Portal Coverage

10 portals are currently scraped:

| Portal | State / Level | Scraper | Notes |
|---|---|---|---|
| **CPPP** (`cppp`) | Central | `CPPP_SCRAPER.PY` | HTML table, paginated |
| **AP eProcurement** (`ap_eprocurement`) | Andhra Pradesh | `AP_scrapper.py` | JSON API |
| **KPPP Karnataka** (`kppp`) | Karnataka | `kpp_Scrapper.py` | REST API (Goods/Works/Services) |
| **Telangana eProcurement** (`telangana_eprocurement`) | Telangana | `Telangana_scrapper.py` | DataTables JSON API |
| **MahaTenders** (`mahatenders`) | Maharashtra | `unified_Scrapper.py` | CAPTCHA-protected |
| **TN Tenders** (`tntenders`) | Tamil Nadu | `unified_Scrapper.py` | CAPTCHA-protected |
| **UP eProcurement** (`up_eprocurement`) | Uttar Pradesh | `unified_Scrapper.py` | CAPTCHA-protected |
| **WB Tenders** (`wbtenders`) | West Bengal | `unified_Scrapper.py` | CAPTCHA-protected |
| **Rajasthan eProcurement** (`rajasthan_eprocurement`) | Rajasthan | `unified_Scrapper.py` | CAPTCHA-protected |
| **Kerala Tenders** (`kerala_tenders`) | Kerala | `unified_Scrapper.py` | CAPTCHA-protected |

The six CAPTCHA-protected portals are handled by `unified_Scrapper.py`, which routes image challenges through the  OCR server before proceeding.

---

## Database Schema

All portals normalize into a single `tenders` table. See `schema.sql` for the full DDL.

### Core Fields

| Field | Type | Description |
|---|---|---|
| `id` | `TEXT PK` | SHA-256 of `portal::tender_ref_no` |
| `tender_ref_no` | `TEXT` | Portal's unique tender identifier |
| `nit_number` | `TEXT` | Notice Inviting Tender number |
| `source_portal` | `TEXT` | Portal slug (e.g. `cppp`, `ap_eprocurement`) |
| `source_url` | `TEXT` | Direct link to tender on source portal |
| `title` | `TEXT` | Tender title / name of work |
| `category` | `TEXT` | `works` \| `goods` \| `services` \| `consultancy` \| `unknown` |
| `buyer_name` | `TEXT` | Issuing organization (leaf of org chain) |
| `buyer_org_chain` | `TEXT` | Full ministry → department hierarchy |
| `state` | `TEXT` | 2-letter state code or `NULL` for central |
| `value` | `NUMERIC` | Estimated contract value in INR |
| `currency` | `TEXT` | Always `INR` |
| `published_at` | `TIMESTAMPTZ` | Date tender was published |
| `deadline_at` | `TIMESTAMPTZ` | Bid submission closing date |
| `opening_at` | `TIMESTAMPTZ` | Tender opening date (where available) |
| `status` | `TEXT` | `open` \| `closed` \| `cancelled` \| `awarded` |
| `corrigendum` | `BOOLEAN` | Whether a corrigendum has been issued |
| `scraped_at` | `TIMESTAMPTZ` | Last time this record was fetched |
| `is_deleted` | `BOOLEAN` | Soft delete flag |
| `portal_metadata` | `JSONB` | Portal-specific extra fields |

### Field Mapping by Portal

| Unified Field | CPPP | AP Portal | State Portals |
|---|---|---|---|
| `id` | SHA-256(cppp::tender_id) | SHA-256(ap::tender_number) | SHA-256(portal::Tender ID) |
| `title` | Title col | `title` field | Tender Title col |
| `buyer_name` | Organisation (last segment) | department (last segment) | Department Name col |
| `value` | Tender Value — strip `₹,` | `tender_value` — strip `₹,` | Estimated Value (ECV) |
| `published_at` | e-Published Date | `published_date` | Published Date col |
| `deadline_at` | Bid Submission Closing Date | `closing_date` | Closing Date col |
| `state` | Derived from org chain | `"AP"` (hardcoded) | Hardcoded per portal |

---

## Project Structure

```
.
├── main.py                        # Scraper orchestrator (runs all scrapers in sequence)
├── main.py (backend)              # FastAPI backend — serves /api/* endpoints
├── CPPP_SCRAPER.PY                # Central CPPP portal scraper
├── AP_scrapper.py                 # Andhra Pradesh eProcurement scraper
├── kpp_Scrapper.py                # Karnataka KPPP scraper (Goods / Works / Services)
├── Telangana_scrapper.py          # Telangana eProcurement scraper
├── unified_Scrapper.py            # Unified scraper for 6 CAPTCHA-protected portals
├── ocr_server.py                  # FastAPI OCR microservice (ddddocr)
├── schema.sql                     # PostgreSQL DDL for the tenders table
├── index.html                     # Dashboard frontend
└── unified_schema_field_mapping.html  # Field mapping reference doc
```

---

## Setup & Installation

### Prerequisites

- Python 3.11+
- PostgreSQL (or a Supabase project)
- A `.env` file with `DATABASE_URL`

### 1. Clone & install dependencies

```bash
git clone https://github.com/your-org/chardi-ai.git
cd chardi-ai

pip install fastapi uvicorn psycopg2-binary python-dotenv \
            requests beautifulsoup4 playwright python-dateutil \
            ddddocr
```

For portals that require browser automation:

```bash
playwright install chromium
```

### 2. Configure environment

```bash
cp .env.example .env
```

```env
DATABASE_URL=postgresql://user:password@host:5432/dbname
```

### 3. Initialize the database

```bash
psql $DATABASE_URL -f schema.sql
```

### 4. Start the OCR server

The OCR server must be running before launching scrapers for CAPTCHA-protected portals.

```bash
uvicorn ocr_server:app --host 127.0.0.1 --port 8000
```

### 5. Run the scrapers

```bash
python main.py        # runs all scrapers sequentially
# or individually:
python CPPP_SCRAPER.PY
python AP_scrapper.py
python kpp_Scrapper.py
python Telangana_scrapper.py
python unified_Scrapper.py
```

### 6. Start the API backend

```bash
uvicorn main:app --reload --port 8000
# Production (Railway sets $PORT automatically):
uvicorn main:app --host 0.0.0.0 --port $PORT
```

---

## Scraper Schedule

All scrapers are deployed on **Railway** and run on a daily cron at **2:00 AM IST** via Railway's built-in cron scheduler. Each scraper uses a 1-day backfill window (`BACKFILL_DAYS = 1`) — it only fetches tenders published in the last 24 hours and upserts them using `ON CONFLICT (id) DO UPDATE`, so re-runs are safe and idempotent.

---

## OCR / CAPTCHA Server

Six portals (Maharashtra, Tamil Nadu, Uttar Pradesh, West Bengal, Rajasthan, Kerala) protect their listing pages with image CAPTCHAs. The `unified_Scrapper.py` resolves these by POSTing the CAPTCHA image to the local OCR microservice.

**Endpoint:** `POST /v1/decode-captcha`

**Request:** `multipart/form-data` with a `file` field containing the CAPTCHA image bytes.

**Response:**
```json
{
  "status": "success",
  "prediction": "X7K2"
}
```

The server uses **ddddocr** — a lightweight neural network optimized for alphanumeric CAPTCHAs common on Indian government portals. It is deployed as a separate Railway service alongside the scrapers.

---

## API Reference

Base URL: deployed on Railway (set in your dashboard config)

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/tenders` | Paginated tender list with filters |
| `GET` | `/api/tenders/{id}` | Single tender detail |
| `GET` | `/api/tenders/export` | Bulk export as CSV or JSON (max 5,000) |
| `GET` | `/api/stats` | Aggregate counts and total value |
| `GET` | `/api/chart/state` | Tender counts grouped by state |
| `GET` | `/health` | Health check |

### Query Parameters — `/api/tenders`

| Parameter | Type | Description |
|---|---|---|
| `q` | string | Full-text search across title, description, buyer |
| `status` | string | `open` \| `closed` \| `cancelled` \| `all` |
| `state` | string | 2-letter state code or `central` |
| `portal` | string[] | One or more portal slugs |
| `buyer_type` | string[] | `central_ministry` \| `psu` \| `state_govt` \| `defence` |
| `min_value` / `max_value` | float | INR value range |
| `deadline_after` / `deadline_before` | ISO date | Date range filter |
| `sort_by` | string | `published_at` \| `deadline_at` \| `value` (default: `published_at`) |
| `sort_dir` | string | `asc` \| `desc` |
| `page` / `limit` | int | Pagination (max limit: 100) |

---

## AI Usage Notes

This project used AI assistance at two distinct layers:

**Scraper development — Gemini + Claude**
Portal-specific scraper logic (parsing HTML tables, reverse-engineering DataTables APIs, handling pagination edge cases, building CAPTCHA bypass flows) was developed using both Gemini and Claude. Each portal required a unique approach; AI was used to accelerate initial scaffolding and debug response parsing.

**Dashboard — Claude**
The frontend dashboard (`index.html`) — including filter UI, charts, pagination, and CSV/JSON export — was built with Claude.

All generated code was reviewed, tested, and adapted to handle the specific quirks of each Indian government portal.

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Database** | PostgreSQL via Supabase |
| **Backend / API** | FastAPI + psycopg2 |
| **Scrapers** | Python — `requests`, `playwright`, `BeautifulSoup` |
| **OCR Server** | FastAPI + `ddddocr` |
| **Dashboard** | HTML, CSS, JavaScript (vanilla) |
| **Frontend Hosting** | Netlify |
| **Backend + Scraper Hosting** | Railway |
| **Cron Scheduling** | Railway Cron Jobs (2:00 AM IST daily) |

---

## License

MIT
