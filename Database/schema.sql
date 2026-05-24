-- ============================================================================
-- CHARDI.AI - GOVERNMENT TENDER PLATFORM
-- Unified Production Schema — All Indian Portals
-- Safe Re-runnable | Supabase/PostgreSQL
-- ============================================================================

-- ============================================================================
-- EXTENSIONS
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ============================================================================
-- TENDERS TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS tenders (

    -- ------------------------------------------------------------------------
    -- PRIMARY IDENTIFIERS
    -- ------------------------------------------------------------------------

    id TEXT PRIMARY KEY,
    -- SHA256(source_portal::tender_ref_no)
    -- Deterministic — safe to upsert repeatedly, never changes for same tender

    tender_ref_no TEXT NOT NULL,
    -- Portal's own reference number as-is
    -- CPPP          → tender_id col        e.g. 2024_MoD_123456_1
    -- GeM           → Bid / RA Number      e.g. GEM/2026/B/7402680
    -- AP portal     → tender_number        e.g. 935699
    -- State portals → Tender ID col
    -- IREPS         → Tender ID col

    nit_number TEXT,
    -- NIT / IFB / Notice number where portals provide it separately
    -- CPPP          → tender_ref_no col (different from tender_id)
    -- AP portal     → nit_number field     e.g. 05/MD/CE/AGICL/2026/2
    -- IREPS         → Notice/IFB Number col
    -- Others        → NULL

    source_portal TEXT NOT NULL,
    -- Allowed values:
    -- cppp | gem | ireps | mahatenders | eproc_karnataka | tntenders
    -- gujarat_eproc | etender_up | telangana | wbtenders
    -- eproc_rajasthan | etenders_kerala | ap_eprocurement

    source_url TEXT,
    -- Full URL to the tender detail page
    -- Required by brief — users click this to verify / download docs

    CONSTRAINT unique_portal_tender
    UNIQUE(source_portal, tender_ref_no),

    -- ------------------------------------------------------------------------
    -- BASIC TENDER DATA
    -- ------------------------------------------------------------------------

    title TEXT,
    -- Unified tender name / work description. Used in full-text search.
    -- CPPP          → Title col
    -- GeM           → Items / Category (bid title)
    -- AP portal     → title field
    -- IREPS         → Name of Work col
    -- State portals → Tender Title col

    description TEXT,
    -- Full scope of work. NULL until Pass 2 (detail page fetch).
    -- AP portal gives this in title field (very long) — split accordingly

    category TEXT,
    -- Normalised procurement type
    -- Allowed: works | goods | services | consultancy | mixed | unknown
    -- AP portal     → category field "WORKS" → "works"
    -- GeM           → classify from Items/Category text
    -- CPPP          → infer from title if not given

    industry TEXT,
    -- Sector classification for dashboard filter
    -- Allowed: it | railways | construction | healthcare | defence
    --          education | energy | water | transport | unknown
    -- Derive from title + buyer_name heuristic

    procurement_type TEXT,
    -- Tender method
    -- Allowed: open_tender | limited_tender | rfq | rfp | gem_bid | rate_contract
    -- GeM           → always gem_bid
    -- CPPP          → open_tender by default unless stated
    -- State portals → infer from title / portal metadata

    status TEXT DEFAULT 'open',
    -- Lifecycle status
    -- Allowed: open | closed | cancelled | awarded
    -- Derive from deadline_at if portal doesn't give explicit status:
    --   deadline_at > NOW()  → open
    --   deadline_at < NOW()  → closed

    corrigendum BOOLEAN DEFAULT FALSE,
    -- TRUE if this tender has amendments published
    -- CPPP          → Corrigendum col — any value ≠ "N/A" → TRUE
    -- Others        → FALSE unless explicitly stated

    -- ------------------------------------------------------------------------
    -- BUYER INFORMATION
    -- ------------------------------------------------------------------------

    buyer_name TEXT,
    -- Most specific government entity name available
    -- CPPP          → Organisation col
    -- GeM           → Department Name (more specific than Ministry Name)
    -- AP portal     → last segment of department field
    -- IREPS         → Department/Location col
    -- State portals → Organisation Chain last segment

    buyer_type TEXT,
    -- Classification of the buying entity
    -- Allowed: central_ministry | state_govt | psu | defence
    --          autonomous_body | local_body | unknown
    -- Derive by heuristic:
    --   "ltd"/"limited"/"corporation"/"bhel"/"ongc" → psu
    --   "state"/"pradesh"/"maharashtra" in name     → state_govt
    --   "army"/"navy"/"air force"                   → defence
    --   default                                     → central_ministry

    buyer_department TEXT,
    -- Department name one level above buyer_name where available
    -- GeM           → Department Name col
    -- AP portal     → department field (full string)

    buyer_org_chain TEXT,
    -- Full ministry → department → org hierarchy as single string
    -- CPPP          → Organisation Chain col  e.g. "MoD >> Army >> Engineers"
    -- GeM           → Ministry Name >> Department Name
    -- Others        → NULL if not available

    buyer_id TEXT,
    -- Portal's internal buyer / organisation ID where given
    -- AP portal → ids.work_id or portal buyer code
    -- Others    → NULL

    buyer_address TEXT,
    -- Physical address of the buying organisation
    -- Available on some state portals and IREPS detail pages
    -- NULL until Pass 2

    state TEXT,
    -- 2-letter ISO 3166-2:IN subdivision code
    -- e.g. MH | TN | UP | KA | AP | GJ | RJ | KL | WB | TG
    -- NULL for central portals (GeM central, CPPP central, IREPS)
    -- Hardcode per portal for state-specific portals:
    --   mahatenders → MH | tntenders → TN | etender_up → UP
    --   eproc_karnataka → KA | ap_eprocurement → AP
    --   gujarat_eproc → GJ | eproc_rajasthan → RJ
    --   etenders_kerala → KL | wbtenders → WB | telangana → TG

    location TEXT,
    -- City / district level location where provided
    -- IREPS / some state portals → Department/Location col
    -- NULL if not available

    -- ------------------------------------------------------------------------
    -- FINANCIAL DATA
    -- ------------------------------------------------------------------------

    value NUMERIC,
    -- Estimated tender value in INR — plain number, no symbols
    -- Strip ₹ comma spaces before storing
    -- "₹ 5,32,92,46,270" → 532924627000
    -- NULL if not published — NEVER store 0 for missing value
    -- CPPP          → Tender Value (₹) col
    -- GeM           → from detail page
    -- AP portal     → tender_value field
    -- IREPS         → Estimated Value (₹) col
    -- State portals → Estimated Value (ECV) col

    currency TEXT DEFAULT 'INR',
    -- ISO 4217 code — always "INR" for all Indian portals
    -- Stored explicitly to satisfy brief requirement

    emd_amount NUMERIC,
    -- Earnest Money Deposit — from detail page
    -- NULL until Pass 2 or if not applicable

    fee_amount NUMERIC,
    -- Tender document / processing fee — from detail page
    -- NULL until Pass 2 or if not applicable

    quantity TEXT,
    -- GeM-specific: quantity of items being procured
    -- GeM           → Quantity col  e.g. "50 Nos" / "100 MT"
    -- Others        → NULL

    -- ------------------------------------------------------------------------
    -- IMPORTANT DATES
    -- All dates stored as TIMESTAMPTZ in IST (UTC+05:30)
    -- Input formats vary per portal — normalise ALL to ISO 8601:
    --   "18/05/2026 08:30 PM" → 2026-05-18T20:30:00+05:30
    --   "22-May-2026 12:30"   → 2026-05-22T12:30:00+05:30
    --   "2026-05-22T12:30:00" → 2026-05-22T12:30:00+05:30
    -- Store NULL if date is missing or unparseable — never store raw string
    -- ------------------------------------------------------------------------

    published_at TIMESTAMPTZ,
    -- When the tender was first published
    -- CPPP          → e-Published Date col
    -- GeM           → Start Date (IST) col
    -- AP portal     → published_date field
    -- State portals → Published Date col / e-Published Date col

    deadline_at TIMESTAMPTZ,
    -- Bid submission closing date — most critical date for users
    -- CPPP          → Bid Submission Closing Date col
    -- GeM           → End Date (IST) col
    -- AP portal     → closing_date field
    -- IREPS         → Submission Deadline col
    -- State portals → Bid Submission Closing Date col

    bid_opening_at TIMESTAMPTZ,
    -- Date when submitted bids are opened by the buyer
    -- CPPP          → Tender Opening Date col
    -- GeM           → not always available
    -- State portals → Tender Opening Date col
    -- NULL if not provided

    -- ------------------------------------------------------------------------
    -- JSON DATA
    -- ------------------------------------------------------------------------

    documents JSONB DEFAULT '[]'::jsonb,
    -- Array of document objects from detail page
    -- Schema: [{ "name": "NIT.pdf", "url": "https://...", "type": "nit" }]
    -- NULL until Pass 2

    raw_data JSONB DEFAULT '{}'::jsonb,
    -- Complete raw scraped response stored as-is
    -- Used for debugging and re-normalisation without re-scraping
    -- Store the full row dict before any transformation

    portal_metadata JSONB DEFAULT '{}'::jsonb,
    -- Portal-specific fields that don't fit the unified schema
    -- AP portal → { "work_id": "816212", "procurement_type": "101", "tender_id": "814892" }
    -- GeM       → { "parent_bid_number": "...", "ra_number": "..." }
    -- CPPP      → { "sl_no": "1", "metadata_ref_id": "..." }

    -- ------------------------------------------------------------------------
    -- TRACKING
    -- ------------------------------------------------------------------------

    detail_scraped BOOLEAN DEFAULT FALSE,
    -- FALSE = only listing-page data so far (Pass 1 complete)
    -- TRUE  = detail page also fetched and merged (Pass 2 complete)
    -- Re-run query: SELECT * FROM tenders WHERE detail_scraped = FALSE

    is_deleted BOOLEAN DEFAULT FALSE,
    -- Soft delete — set TRUE for cancelled/withdrawn tenders
    -- Never hard-delete rows; keeps audit trail intact

    created_at TIMESTAMPTZ DEFAULT NOW(),

    updated_at TIMESTAMPTZ DEFAULT NOW(),

    scraped_at TIMESTAMPTZ DEFAULT NOW()
    -- Last time scraper touched this row — shows data freshness

);

-- ============================================================================
-- SAFE COLUMN MIGRATIONS
-- (Safe to re-run if table already exists from older version)
-- ============================================================================

ALTER TABLE tenders ADD COLUMN IF NOT EXISTS nit_number TEXT;
ALTER TABLE tenders ADD COLUMN IF NOT EXISTS buyer_org_chain TEXT;
ALTER TABLE tenders ADD COLUMN IF NOT EXISTS buyer_address TEXT;
ALTER TABLE tenders ADD COLUMN IF NOT EXISTS location TEXT;
ALTER TABLE tenders ADD COLUMN IF NOT EXISTS emd_amount NUMERIC;
ALTER TABLE tenders ADD COLUMN IF NOT EXISTS fee_amount NUMERIC;
ALTER TABLE tenders ADD COLUMN IF NOT EXISTS quantity TEXT;
ALTER TABLE tenders ADD COLUMN IF NOT EXISTS corrigendum BOOLEAN DEFAULT FALSE;
ALTER TABLE tenders ADD COLUMN IF NOT EXISTS detail_scraped BOOLEAN DEFAULT FALSE;
ALTER TABLE tenders ADD COLUMN IF NOT EXISTS industry TEXT;
ALTER TABLE tenders ADD COLUMN IF NOT EXISTS procurement_type TEXT;
ALTER TABLE tenders ADD COLUMN IF NOT EXISTS documents JSONB DEFAULT '[]'::jsonb;
ALTER TABLE tenders ADD COLUMN IF NOT EXISTS raw_data JSONB DEFAULT '{}'::jsonb;
ALTER TABLE tenders ADD COLUMN IF NOT EXISTS portal_metadata JSONB DEFAULT '{}'::jsonb;
ALTER TABLE tenders ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE tenders ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE tenders ADD COLUMN IF NOT EXISTS scraped_at TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE tenders ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT FALSE;

-- ============================================================================
-- INDEXES
-- ============================================================================

-- Dashboard filter indexes
CREATE INDEX IF NOT EXISTS idx_tenders_portal      ON tenders (source_portal);
CREATE INDEX IF NOT EXISTS idx_tenders_state       ON tenders (state);
CREATE INDEX IF NOT EXISTS idx_tenders_status      ON tenders (status);
CREATE INDEX IF NOT EXISTS idx_tenders_deadline    ON tenders (deadline_at);
CREATE INDEX IF NOT EXISTS idx_tenders_published   ON tenders (published_at);
CREATE INDEX IF NOT EXISTS idx_tenders_value       ON tenders (value);
CREATE INDEX IF NOT EXISTS idx_tenders_buyer_type  ON tenders (buyer_type);
CREATE INDEX IF NOT EXISTS idx_tenders_category    ON tenders (category);
CREATE INDEX IF NOT EXISTS idx_tenders_industry    ON tenders (industry);
CREATE INDEX IF NOT EXISTS idx_tenders_scraped     ON tenders (scraped_at);

-- Composite indexes for common dashboard queries
CREATE INDEX IF NOT EXISTS idx_tenders_state_status
    ON tenders (state, status);

CREATE INDEX IF NOT EXISTS idx_tenders_portal_deadline
    ON tenders (source_portal, deadline_at);

CREATE INDEX IF NOT EXISTS idx_tenders_status_deadline
    ON tenders (status, deadline_at)
    WHERE is_deleted = FALSE;

-- Pass 2 re-run index — only indexes incomplete rows
CREATE INDEX IF NOT EXISTS idx_tenders_detail_pass
    ON tenders (detail_scraped)
    WHERE detail_scraped = FALSE;

-- Full-text search across title + description + buyer
CREATE INDEX IF NOT EXISTS idx_tenders_fts
    ON tenders
    USING GIN (
        to_tsvector(
            'english',
            coalesce(title, '') || ' ' ||
            coalesce(description, '') || ' ' ||
            coalesce(buyer_name, '')
        )
    );

-- Trigram index for partial/fuzzy search on title
CREATE INDEX IF NOT EXISTS idx_tenders_title_trgm
    ON tenders
    USING GIN (title gin_trgm_ops);

-- JSONB indexes
CREATE INDEX IF NOT EXISTS idx_tenders_raw_data
    ON tenders USING GIN (raw_data);

CREATE INDEX IF NOT EXISTS idx_tenders_portal_metadata
    ON tenders USING GIN (portal_metadata);

CREATE INDEX IF NOT EXISTS idx_tenders_documents
    ON tenders USING GIN (documents);

-- ============================================================================
-- UPDATED_AT AUTO TRIGGER
-- ============================================================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_update_tenders_updated_at ON tenders;

CREATE TRIGGER trigger_update_tenders_updated_at
BEFORE UPDATE ON tenders
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- SCRAPE RUNS TABLE
-- Tracks every pipeline execution — required for the metrics summary
-- ============================================================================

CREATE TABLE IF NOT EXISTS scrape_runs (

    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,

    portal TEXT NOT NULL,
    -- Which portal this run targeted

    started_at TIMESTAMPTZ DEFAULT NOW(),

    finished_at TIMESTAMPTZ,

    status TEXT,
    -- running | success | partial | failed

    success_count INTEGER DEFAULT 0,
    -- Number of tenders successfully upserted

    failed_count INTEGER DEFAULT 0,
    -- Number of URLs that landed in scrape_errors

    pages_scraped INTEGER DEFAULT 0,
    -- How many listing pages were fetched

    logs TEXT
    -- Free-text run log for debugging

);

CREATE INDEX IF NOT EXISTS idx_scrape_runs_portal
    ON scrape_runs (portal);

CREATE INDEX IF NOT EXISTS idx_scrape_runs_started
    ON scrape_runs (started_at);

-- ============================================================================
-- SCRAPE ERRORS TABLE
-- Dead-letter log — every failed URL lands here instead of crashing
-- ============================================================================

CREATE TABLE IF NOT EXISTS scrape_errors (

    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,

    portal TEXT,

    url TEXT,

    error_type TEXT,
    -- timeout | captcha | parse_error | http_error | auth_error

    error_msg TEXT,

    retry_count INTEGER DEFAULT 0,
    -- Increment each time this URL is retried

    resolved BOOLEAN DEFAULT FALSE,
    -- Mark TRUE once the URL is successfully re-scraped

    payload JSONB DEFAULT '{}'::jsonb,
    -- Store any partial data retrieved before failure

    failed_at TIMESTAMPTZ DEFAULT NOW()

);

-- Safe migrations for scrape_errors (handles existing tables)
ALTER TABLE scrape_errors ADD COLUMN IF NOT EXISTS resolved BOOLEAN DEFAULT FALSE;
ALTER TABLE scrape_errors ADD COLUMN IF NOT EXISTS retry_count INTEGER DEFAULT 0;
ALTER TABLE scrape_errors ADD COLUMN IF NOT EXISTS payload JSONB DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS idx_scrape_errors_portal
    ON scrape_errors (portal);

CREATE INDEX IF NOT EXISTS idx_scrape_errors_failed_at
    ON scrape_errors (failed_at);

CREATE INDEX IF NOT EXISTS idx_scrape_errors_unresolved
    ON scrape_errors (resolved)
    WHERE resolved = FALSE;

-- ============================================================================
-- OPEN TENDERS VIEW
-- Default dashboard view — active tenders only, newest first
-- ============================================================================

CREATE OR REPLACE VIEW open_tenders AS
    SELECT *
    FROM tenders
    WHERE status = 'open'
      AND is_deleted = FALSE
      AND (deadline_at IS NULL OR deadline_at > NOW())
    ORDER BY published_at DESC;

-- ============================================================================
-- PASS 2 QUEUE VIEW
-- All tenders that still need their detail page fetched
-- ============================================================================

CREATE OR REPLACE VIEW detail_queue AS
    SELECT id, source_portal, source_url, scraped_at
    FROM tenders
    WHERE detail_scraped = FALSE
      AND is_deleted = FALSE
    ORDER BY scraped_at DESC;
