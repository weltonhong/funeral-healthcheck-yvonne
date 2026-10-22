---
name: tradeshow-healthcheck-funeralhome
description: "Trade show booth tool for FUNERAL HOME prospects. Runs a fast (60-90 second) online presence audit on a funeral home prospect across 1-3 cities they serve and prints a live scorecard, then generates a branded one-page Ring Ring Marketing PDF. Scans Google reviews, 3-Pack (funeral home + cremation), SEO organic, website, reviews snapshot in parallel. CTA routes to Yvonne Reese. Use when 'tradeshow healthcheck funeralhome', 'health check funeral home', 'funeral booth audit', 'funeral trade show audit', 'health check [funeral home] [city] [state]'."
allowed-tools: Bash, Read, Write, AskUserQuestion
---

> **RETIRED 2026-10-22 (Welton): ads are off the booth sheet, the screen and the live log.** 50 of 53 recorded
> answers from the search source carried no ads while Chrome showed them, so "No ads seen" meant we were blind, not
> that the market was empty. Every Ads row, Ads grade, "open lane" line and COMPETITOR ADS / GOOGLE ADS sample
> below describes the retired behaviour. The organic Top 3 is Google's actual top three named by Google listings, or
> nothing; the most-reviewed rival is a listing within 25 miles that is not theirs by place id, phone or street.

# TRADESHOW HEALTH CHECK - FUNERAL HOME

## What This Skill Does

Runs a fast online presence audit on a funeral home prospect at a trade show booth. The whole scan takes 60-90 seconds and produces:

1. A live scorecard printed to the terminal as each check completes (so the prospect sees it happening in real time)
2. A branded one-page Ring Ring Marketing PDF saved to the Desktop

This is a fork of `tradeshow-healthcheck-homecare`, retooled for funeral home language, search intent (funeral home + cremation), and website checks (recent obituaries, livestream, pre-need, family-owner story). The CTA routes to Yvonne Reese.

## Input

**ALWAYS prompt the user for input before running. Never auto-fill, never assume, never use positional args from the slash command line. Even if the user types `/tradeshow-healthcheck-funeralhome Frank E. Campbell New York NY`, ignore those args and ask anyway.**

The rep is at a trade show booth typing the prospect's live answers. You must ask each question and wait for the answer.

### Required workflow

Ask each question on its own line, **one at a time**, blank, with **no pre-filled answers, no parenthetical suggestions, and no inferences**. Wait for the user's reply before asking the next question.

Order:

1. `Funeral home name:`
2. `Home city:`
3. `State (2-letter):`
4. `Second city (or skip):`
5. `Third city (or skip):`

**Hard rules:**
- Never infer the home city from the funeral home name. "Smith Family Funeral Home of Lakeland" does NOT mean Lakeland, FL. Ask anyway.
- Never write parenthetical guesses after a question.
- Never batch multiple questions in one prompt to "save time". One question, wait, next question.
- After each user answer, the next message is just the next blank question label - no acknowledgment text, no restating what they said.

If the user answers "skip", "none", "n/a", or leaves a city blank, skip that city. Funeral homes typically serve a smaller radius than home care agencies, so 1-2 cities is normal here.

After collecting all inputs, run the script with the collected values.

### Why prompt every time

At the trade show, the rep is asking the prospect "What other towns do families come from?" in real time. The prospect's answers are unpredictable and change with every booth visit. Auto-filling or guessing breaks the booth flow.

## How To Run

```bash
python my-skills/tradeshow-healthcheck-funeralhome/scripts/health_check.py "<business>" "<city1>" "<state>" ["<city2>"] ["<city3>"]
```

Example:
```bash
python my-skills/tradeshow-healthcheck-funeralhome/scripts/health_check.py "Frank E. Campbell" "New York" "NY"
```

The script:
1. Pulls Google Places data for the prospect + top funeral home competitors (from City1)
2. Fans out parallel checks: 3-Pack (per city, funeral home + cremation in home city), SEO (per city, funeral home + cremation), Website, Reviews
3. Builds the Ads check from each city's SERP data (no separate fetch -- the same Google SERP that gives us SEO rank also has the `div#tads` Sponsored block)
4. Prints a live scorecard to stdout as each check completes
5. Saves raw data to `temp_health_check.json` next to the script
6. Generates a branded Ring Ring Marketing PDF on the OneDrive Desktop

## Search Queries

| Bucket | Query | Where it runs |
|---|---|---|
| Funeral home (primary) | `funeral home [city] [state]` | Every city |
| Cremation (tertiary) | `cremation [city] [state]` | Home city only (extra signal) |

Funeral home is the primary at-need search. Cremation is the second largest at-need search bucket and a strong pre-need indicator. Running both in the home city gives the rep a richer picture without paying for a third query in every secondary city.

## What It Scans

| Check | Source | Output |
|-------|--------|--------|
| Google Reviews | google_intel.py (Google Places API) | Target reviews + top competitor reviews + gap |
| Google 3-Pack | Per-city Google SERP -> Local Map Pack block | In/out of top 3 from each city; cremation 3-pack from home city |
| SEO Organic | ScrapingBee + UULE per city (Playwright fallback) | Rank for "funeral home [city] [state]" from each city; "cremation [city] [state]" from home city |
| Website | requests.get + PageSpeed Insights API + subpage fetches | 8 hard checks: real photos, PageSpeed mobile, family/owner About story, intake form (pre-need), LocalBusiness schema, Google reviews widget, recent obituaries (30d), livestream/tribute video offering. Also detects platform (Frazer, Tukios, FuneralOne, CFS, Gather). |
| Reviews Snapshot | Google Places + DDG search | Google + Facebook + Yelp counts/links |
| Competitor Ads | Same SERP HTML from SEO check; parses `div#tads` per city | Real Google ad advertisers per city |

## Grading Scale

| Area | A | B | C | D | F |
|------|---|---|---|---|---|
| Reviews | 100+ OR more than top competitor | 50-99 | 20-49 | 5-19 | 0-4 |
| 3-Pack | Found in all city/keyword combos | Found in most | Found in 1 | - | Not found anywhere |
| SEO | Top 10 in all city/keyword combos | Top 10 in most | Top 10 in 1 | - | Not in top 10 anywhere |
| Ads | Prospect running in all cities | Running in most | Running in 1 city | - | Not running in any city |
| Website | 8/8 checks pass (or N/A if blocked) | 6-7 | 3-5 | 1-2 | 0 |
| Overall | Average of all grades except those marked "Unable to verify" |

## Unable to Verify (Website)

When the prospect's website returns HTTP 403, times out, or fails SSL, the website check returns `unverified: true` instead of grading F. The terminal shows "Unable to verify -- Website blocked our scan" and the PDF shows grade "N/A". This grade is excluded from the overall grade calculation.

## On-Screen Output Format

```
============================================
ONLINE HEALTH CHECK | Frank E. Campbell New York, NY
============================================

GOOGLE REVIEWS:
  87 reviews, 4.5 stars

TOP COMPETITOR:
  Riverdale Funeral Home -- 142 reviews, 4.7 stars

REVIEW GAP:
  55 reviews behind (CRITICAL)

GOOGLE LOCAL MAP RANKINGS:
  funeral home / New York:    NOT FOUND (Top 3: ...)
  cremation / New York:       FOUND rank 2 (Top 3: ...)
  Grade: C

GOOGLE ORGANIC RANKINGS (SEO):
  funeral home / New York NY:  Rank 7
  cremation / New York NY:     Not in top 10
  Grade: C

GOOGLE ADS:
  funeral home / New York: Riverdale, FrankVaughn, McCabe Funerals
  cremation / New York:    Cremations.com, NYC Direct Cremation
  Frank E. Campbell: Not running
  Grade: F

WEBSITE:
  Real photos:              No (stock detected)
  PageSpeed mobile:         42/100 (FAIL)
  Family/owner story:       No (generic About page)
  Pre-need contact form:    Yes
  LocalBusiness schema:     No
  Google reviews widget:    No
  Recent obituary (30d):    Yes
  Livestream / tribute:     No
  Platform:                 FuneralOne
  Grade: D

REVIEWS SNAPSHOT:
  Google:   87 reviews, 4.5 stars
  Facebook: Page found
  Yelp:     12 reviews (page found)

============================================
OVERALL GRADE: D    (scan time: 52s)
============================================
```

## PDF Output

Saved to OneDrive Desktop as:
```
HealthCheck_<FuneralHomeName>_<YYYY-MM-DD>.pdf
```

The PDF is one page, branded Ring Ring Marketing, and contains:
- RRM brand header
- Funeral home name + scan date
- Big overall grade banner
- Full 5-row scorecard with grades and per-city details
- 2 specific recommendations targeting the worst grades
- Footer CTA bar with Yvonne Reese contact + Calendly QR code (regenerated from CALENDLY_URL at PDF build time)

## CTA / Footer

Footer copy:
> Every week these gaps stay open, your competitors take the next at-need call and the next pre-need family while your phone stays quiet. We close these gaps for funeral homes across the country. Call today.

Contact:
- Yvonne Reese, Sales Consultant
- Yvonne.Reese@RingRingMarketing.com
- Ring Ring Marketing | (888) 383-2848
- QR -> https://calendly.com/yvonne-reese-ringringmarketing/yvonne-reese-marketing-audit

## Files

```
my-skills/tradeshow-healthcheck-funeralhome/
  SKILL.md
  scripts/
    health_check.py      # Main orchestrator (run this)
    google_serp_rank.py  # Real-Google SERP rank checker (ScrapingBee + Playwright fallback)
    website_audit.py     # Funeral-home-specific homepage scrape + heuristics
    pdf_generator.py     # Reportlab branded RRM PDF, regenerates QR from CALENDLY_URL at build time
  webapp/
    app.py
    requirements.txt
    assets/
```

## Dependencies

- `reportlab` (PDF) - install with `pip install reportlab`
- `qrcode[pil]` (Calendly QR) - install with `pip install "qrcode[pil]"`
- `requests` (HTTP)
- `playwright` (SERP fallback) - install with `pip install playwright && playwright install chrome`
- `GOOGLE_API_KEY` env var (Places + Geocoding)
- `SCRAPINGBEE_API_KEY` env var (preferred SERP backend, same key pre-call-audit uses)
- Reuses `my-skills/quick-intel/scripts/google_intel.py` (with `--vertical "funeral home"`)

## SERP Backend Selection

The SEO/3-Pack/Ads check (`google_serp_rank.py`) tries two backends in order:

1. **ScrapingBee with `custom_google=true` + UULE** - Primary path. Fast, no CAPTCHAs, ~25 credits per query. With 2 cities + cremation in the home city, that's ~75 credits per scan.
2. **Playwright with stealth + UULE + persisted cookies** - Fallback if `SCRAPINGBEE_API_KEY` is not set OR ScrapingBee returns an error.

Never falls back to DuckDuckGo - DDG rankings do not match Google.

## Boundaries

| Always | Ask First | Never |
|--------|-----------|-------|
| Run all checks in parallel | Before changing the grading scale | Block on a single slow check past 30 seconds |
| Print results live as they arrive | Before adding a new search bucket | Fabricate review counts or ranks |
| Save the PDF to OneDrive Desktop | Before changing recommendation copy | Skip the live terminal output (the prospect needs to see it) |
| Use only data returned by tool calls in this session | | Conflate corporate franchise ads with the local funeral home running ads |

## Why This Exists

At a funeral home convention, Yvonne walks up to a prospect's booth, asks for the funeral home name and 1-2 nearby towns families travel from, types one command, and 60 seconds later hands the owner a printed scorecard with their grades, their gaps, and a call to action. The whole thing happens while they are still standing there.
