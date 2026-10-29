"""
Website Audit - Trade Show Health Check (Funeral Home Edition, Hard Mode)

Fetches a homepage and runs 7 hard checks designed to surface real issues
the prospect doesn't know about. These are intentionally strict so most
funeral home sites do not score an A.

Checks:
  1. Real photos (no stock photo CDNs / generic alt text). Funeral homes
     are particularly stock-heavy (candles, white roses, "elderly hands"),
     so we lean even harder on this signal.
  2. PageSpeed mobile score >= 50 (Google PageSpeed Insights API)
  3. Family/owner About page that names actual people with a real story
     (replaces the homecare "team page" check -- funeral homes are
     deeply relationship-based, generic boilerplate "About" pages are a
     real gap).
  4. Pre-need contact form / pre-arrangement page (replaces the homecare
     "intake form" check -- pre-need is the highest-margin vertical for
     funeral homes).
  5. LocalBusiness schema markup (or a relevant subtype, e.g. FuneralHome).
  6. Google reviews widget embedded on the site.
  7. Recent obituary posted in the last 30 days (NEW -- a stale obit page
     signals the website is not actively maintained, which families notice).
  (A livestream / tribute video check was removed, Welton 2026-10-29: livestreaming is the funeral
  home's own service and not one we sell, so it is not measured, printed or graded.)

We also detect the platform when possible (Frazer, Tukios, FuneralOne,
CFS, Gather) and surface it as a sales-call data point. Platform is NOT
graded.

Grade: share of the 7 checks passed, scaled to 8: A (8/8), B (6-7), C (3-5), D (1-2), F (0)

Usage:
    python website_audit.py --url https://example.com
"""

import argparse
import datetime
import json
import os
import re
import threading
import subprocess
import sys
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

import requests

import site_reader   # the shared site reader, pinned byte-identical across the five tools (2026-10-29)


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# ----------------------------- helpers -----------------------------


def get_google_api_key():
    key = os.environ.get("GOOGLE_API_KEY", "")
    if key:
        return key
    try:
        result = subprocess.run(
            ["powershell", "-Command",
             "[System.Environment]::GetEnvironmentVariable('GOOGLE_API_KEY', 'User')"],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip()
    except Exception:
        return ""



# ---- "Couldn't check", never "No" from a page nobody read (Welton, 2026-10-20) ----------------------
# A check used to answer No whenever a page it needed could not be read (blocked, rate-limited, server
# error, no connection), and when a site refused the address probes. Now every fetch and probe made
# while a check runs notes the pages it could not read, and measured() turns that check's No into None
# ("Couldn't check"). A Yes stands (it was seen); a page that is not there (404/410) is still a No.

# ---- A homepage that loads with almost nothing readable is built in the browser (Welton, 2026-10-20) ----
# Measured on 200 sites from the saved runs (ops/receipts/20261020T171217_script-built-homepages-measured.txt):
# 19 of 81 funeral home homepages came back with 18 to 65 readable characters (one platform: Tribute /
# FrontRunner / FuneralTech) and 1,000 to 8,000 once a browser ran their scripts; the thinnest real page
# had 415. The booth printed 2 to 4 "No"s on each, 13 of them provably false ("Pre-need form: No" beside
# a pre-planning link). Under MIN_READABLE_CHARS the website reads "Couldn't check", no grade.
MIN_READABLE_CHARS = 200
SCRIPT_BUILT_REASON = "Couldn't check (site loads its content in the browser)"


def readable_chars(html):
    t = re.sub(r"(?is)<(script|style|noscript|template)\b.*?</\1>", " ", html or "")
    t = re.sub(r"(?s)<!--.*?-->", " ", t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"&[a-z#0-9]+;", " ", t)
    return len(" ".join(t.split()))

_reads = threading.local()


def _note_unread(url, why):
    unread = getattr(_reads, "unread", None)
    if unread is not None:
        unread.append((url, why))


def measured(check, *args):
    """Run one check. Its No becomes None when a page it needed could not be read."""
    _reads.unread = []
    try:
        result = check(*args)
    finally:
        unread, _reads.unread = _reads.unread, None
    if not unread:
        return result
    if result is False or result is None:
        return None
    if isinstance(result, dict) and not result.get("pass"):
        return dict(result, **{"pass": None})
    if isinstance(result, tuple) and result and not result[0]:
        return (None,) + tuple(result[1:])
    return result


def fetch_page(url, timeout=15):
    if not url:
        return None, None, "no url"
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        if r.status_code in (401, 403, 407, 429) or r.status_code >= 500:
            _note_unread(url, "HTTP %s" % r.status_code)
        return r.text, r.status_code, r.url
    except Exception as e:
        _note_unread(url, str(e)[:80])
        return None, None, str(e)


def base_origin(url):
    """Return scheme://host of a URL."""
    try:
        p = urllib.parse.urlparse(url)
        return f"{p.scheme}://{p.netloc}"
    except Exception:
        return ""


def find_internal_link(html, base_url, url_keywords):
    """Find first <a href> whose path contains any of the keywords."""
    if not html or not base_url:
        return None
    # href="...", href='...' or href=... are all links (Welton 2026-10-21: a site whose links use single
    # quotes read "No" for a team page, blog, pre-need form, obituary page, gallery or livestream it has).
    pattern = re.compile(r"""<a[^>]+href\s*=\s*["']?([^"'\s>]+)""", re.IGNORECASE)
    for m in pattern.finditer(html):
        href = m.group(1).strip()
        if href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        href_low = href.lower()
        for kw in url_keywords:
            if kw in href_low:
                if href.startswith("http"):
                    url = href
                elif href.startswith("//"):
                    url = "https:" + href
                elif href.startswith("/"):
                    url = base_url + href
                else:
                    url = urllib.parse.urljoin(base_url + "/", href)
                if site_reader.same_site(url, base_url):
                    return url
                # Another site's page is not theirs (Welton 2026-10-29): not read, and a No that needed it is
                # "couldn't check". Look at the next link.
                _note_unread(url, "another site")
                break
    return None


def find_internal_link_by_path(html, base_url, paths):
    """Try a fixed list of candidate paths against the base URL even if no
    matching href appeared on the homepage. Returns the first that fetches
    a 2xx response, else None."""
    if not base_url:
        return None
    for p in paths:
        url = base_url.rstrip("/") + p
        try:
            r = requests.head(url, headers=HEADERS, timeout=8, allow_redirects=True)
            if r.status_code and 200 <= r.status_code < 300:
                return r.url
            if r.status_code not in (404, 410):
                _note_unread(url, "HEAD %s" % r.status_code)   # the site would not say; not "no page"
        except Exception as e:
            _note_unread(url, str(e)[:80])
            continue
    return None


# ----------------------------- 1. Real photos vs stock -----------------------------

STOCK_INDICATORS = [
    # Stock provider CDNs and URLs
    "shutterstock", "istockphoto", "gettyimages", "stock.adobe",
    "depositphotos", "dreamstime", "123rf.com", "alamy.com", "bigstock",
    "fotolia", "unsplash.com", "pexels.com", "pixabay.com",
    "stocksnap.io", "freepik.com", "canva.com/photos",
    # Common stock filename patterns
    "stock-photo", "stock_photo", "/stock/", "shutterstock_",
    "istock_", "gettyimages-",
]

# Funeral-vertical generic alt patterns. Heavier emphasis on candles,
# roses, and "elderly hands" because this vertical is stock-heavy.
GENERIC_ALT_PATTERNS = [
    r'alt="[^"]*candle',
    r'alt="[^"]*white\s+rose',
    r'alt="[^"]*white\s+flowers?',
    r'alt="[^"]*elderly\s+hands',
    r'alt="[^"]*clasped\s+hands',
    r'alt="[^"]*holding\s+hands',
    r'alt="[^"]*bible',
    r'alt="[^"]*cross\s+(silhouette|sunset)',
    r'alt="[^"]*coffin',
    r'alt="[^"]*grieving',
    r'alt="[^"]*tombstone',
    r'alt="[^"]*headstone',
    r'alt="[^"]*funeral\s+wreath',
    r'alt="[^"]*sympathy\s+flowers?',
    r'alt="[^"]*sad\s+(woman|man|person)',
    r'alt="[^"]*sunset\s+(silhouette|cross)',
]


def check_real_photos(html):
    """Return True if NO stock photo indicators found. Bias even harder
    on this vertical -- a single stock-CDN hit OR two generic alts is
    enough to fail."""
    html_lower = html.lower()
    for hint in STOCK_INDICATORS:
        if hint in html_lower:
            return False
    generic_alt_hits = 0
    for pat in GENERIC_ALT_PATTERNS:
        if re.search(pat, html_lower):
            generic_alt_hits += 1
            if generic_alt_hits >= 2:
                return False
    return True


# ----------------------------- 2. PageSpeed Insights -----------------------------


PSI_RUNS = 5          # Google's speed test runs per scan, all at once
PSI_MIN_RUNS = 3      # fewer back than this is couldn't check


def check_pagespeed(url, api_key, timeout=90):
    """Google's mobile speed test, run PSI_RUNS times at once (Welton 2026-10-22).

    One run is not a measurement. Six fresh runs of one page within a minute scored 30 to 57 (Forest Lawn), 41 to 55
    (Veritas) and 40 to 62 (Haven); the sheets had printed one run each (26, 37, 52), and Veritas's "slow page" bullet
    fired on a page Google's own site scored 54. Each run gets its own address (a harmless rrm_psi tag): Google hands
    back its cached answer for an address it tested moments ago, so five runs of one address are one run.

    Returns the runs' low and high. score is the HIGH run and pass is high >= 50, so nothing calls a page slow unless
    every run said so: the owner can run the test himself, and one good run of his disproves a slow claim built on a
    bad run of ours. Fewer than PSI_MIN_RUNS runs back is couldn't check (score None), never a verdict.
    """
    if not api_key:
        sys.stderr.write("[pagespeed] no GOOGLE_API_KEY available\n")
        return {"score": None, "pass": None, "error": "no api key"}
    if not url:
        return {"score": None, "pass": None, "error": "no url"}

    def one(n):
        base, hash_, frag = url.partition("#")
        tagged = base + ("&" if "?" in base else "?") + "rrm_psi=%d" % n + hash_ + frag
        try:
            r = requests.get("https://www.googleapis.com/pagespeedonline/v5/runPagespeed", timeout=timeout,
                             params={"url": tagged, "strategy": "mobile", "category": "performance", "key": api_key})
            if r.status_code != 200:
                return None, "HTTP %s: %s" % (r.status_code, r.text[:160])
            score = r.json().get("lighthouseResult", {}).get("categories", {}).get("performance", {}).get("score")
            return (None, "no score in response") if score is None else (round(score * 100), None)
        except Exception as e:
            return None, str(e)[:200]

    with ThreadPoolExecutor(max_workers=PSI_RUNS) as ex:
        runs = list(ex.map(one, range(1, PSI_RUNS + 1)))
    scores = sorted(s for s, _ in runs if s is not None)
    errors = [e for _, e in runs if e]
    for e in errors:
        sys.stderr.write("[pagespeed] a run failed for %s: %s\n" % (url, e))
    if len(scores) < PSI_MIN_RUNS:
        return {"score": None, "pass": None, "scores": scores,
                "error": "only %d of %d speed tests came back%s" % (len(scores), PSI_RUNS, (": " + errors[0]) if errors else "")}
    return {"score": scores[-1], "low": scores[0], "high": scores[-1], "scores": scores, "pass": scores[-1] >= 50}


# ----------------------------- 3. Family/owner About story -----------------------------

ABOUT_URL_KEYWORDS = [
    "/about", "/our-story", "/our-history", "/who-we-are", "/family",
    "/our-family", "/ownership",
]
ABOUT_PATH_FALLBACKS = [
    "/about", "/about-us", "/our-story", "/who-we-are", "/our-history",
    "/our-family",
]
# Signals that a real family/owner is named on the page, not just generic
# "we have served families since 1923" boilerplate.
FAMILY_OWNER_SIGNALS = [
    r"\bowner\b",
    r"\bowners\b",
    r"\b(co[- ])?founder\b",
    r"\bfuneral\s+director\b",
    r"\bdirector\s+of\s+funeral",
    r"\b(?:third|second|fourth|fifth|sixth)\s+generation",
    r"\b\d(?:st|nd|rd|th)\s+generation\b",
    r"\bfamily[- ]owned\b",
    r"\bfamily[- ]operated\b",
    r"\bproudly\s+family",
    r"\bestablished\s+(?:in\s+)?\d{4}\b",
    r"\bsince\s+\d{4}\b",
    r"\b(grandfather|grandmother|father|mother|son|daughter|grandson|granddaughter)\b",
    r"\bcontinues\s+the\s+legacy\b",
    r"\bcarrying\s+on\s+the\s+legacy\b",
]


def _family_signal_count(html):
    text = re.sub(r"<[^>]+>", " ", html or "").lower()
    text = re.sub(r"\s+", " ", text)
    return sum(1 for pat in FAMILY_OWNER_SIGNALS if re.search(pat, text))


def check_family_owner_story(home_html, base_url):
    """Pass if the About page (or a story page) names actual family/owner
    figures with at least 2 strong family-business signals.

    Generic boilerplate without a named owner does NOT pass."""
    # The homepage counts too (Welton 2026-10-20): La Paloma's says "a family-owned and operated
    # funeral home" and "locally owned since 2006", and the sheet printed "No (generic About page)"
    # because only the About page was read.
    if _family_signal_count(home_html) >= 2:
        return True
    about_url = (
        find_internal_link(home_html, base_url, ABOUT_URL_KEYWORDS)
        or find_internal_link_by_path(home_html, base_url, ABOUT_PATH_FALLBACKS)
    )
    if not about_url:
        about_url = base_url

    page_html, status, _ = fetch_page(about_url, timeout=10)
    if not page_html or not status or status >= 400:
        if about_url != base_url:
            page_html = home_html
        else:
            return False

    text = re.sub(r"<[^>]+>", " ", page_html or "").lower()
    text = re.sub(r"\s+", " ", text)
    hits = 0
    for pat in FAMILY_OWNER_SIGNALS:
        if re.search(pat, text):
            hits += 1
            if hits >= 2:
                return True
    return False


# ----------------------------- 4. Pre-need contact form -----------------------------

PRENEED_URL_KEYWORDS = [
    "/pre-need", "/preneed", "/pre-arrangement", "/pre-arrange",
    "/prearrange", "/pre-plan", "/preplan", "/pre-planning", "/preplanning",
    "/plan-ahead", "/planahead", "/planning-ahead", "/advance-planning",
    "/funeral-planning", "/cremation-planning",
]
PRENEED_PATH_FALLBACKS = [
    "/preplanning", "/pre-planning", "/preneed", "/pre-need",
    "/plan-ahead", "/pre-arrangement", "/pre-arrangements",
    "/funeral-planning",
]
PRENEED_FORM_HINTS = [
    "preneed", "pre-need", "pre-plan", "preplan", "pre-arrange",
    "prearrange", "pre-planning", "preplanning", "advance planning",
    "funeral planning", "plan ahead", "planning ahead",
]
SCHEDULING_HINTS = [
    "calendly.com", "acuityscheduling", "squareup.com/appointments",
    "jotform.com", "gravityforms", "wpforms", "wpcf7", "contact-form-7",
    "hubspot.com/forms", "hsforms.com", "typeform.com", "ninjaforms",
    "formstack", "fluentform", "wsform", "fluent-form", "gform_wrapper",
    "elfsight-app-form",
]


def check_preneed_form(home_html, base_url):
    """Pass if the site has a pre-need / pre-arrangement page reachable
    from the homepage AND that page has a real form (or a scheduling
    widget / substantial pre-need content)."""
    pn_url = (
        find_internal_link(home_html, base_url, PRENEED_URL_KEYWORDS)
        or find_internal_link_by_path(home_html, base_url, PRENEED_PATH_FALLBACKS)
    )
    if not pn_url:
        return False
    page_html, status, _ = fetch_page(pn_url, timeout=10)
    if not page_html or not status or status >= 400:
        return False
    page_lower = page_html.lower()

    for h in SCHEDULING_HINTS:
        if h in page_lower:
            return True

    forms = re.findall(r"<form\b[^>]*>(.*?)</form>", page_html, re.IGNORECASE | re.DOTALL)
    for form in forms:
        form_low = form.lower()
        if 'role="search"' in form_low or 'type="search"' in form_low:
            continue
        if 'class="searchform' in form_low or 'id="searchform' in form_low:
            continue
        inputs = re.findall(r"<(input|textarea|select)\b[^>]*>", form, re.IGNORECASE)
        hidden = len(re.findall(r'<input[^>]+type=["\']hidden["\']', form, re.IGNORECASE))
        submit = len(re.findall(r'<input[^>]+type=["\']submit["\']', form, re.IGNORECASE))
        real_inputs = len(inputs) - hidden - submit
        if real_inputs >= 3:
            return True

    text = re.sub(r"<[^>]+>", " ", page_html).lower()
    pn_hits = sum(1 for h in PRENEED_FORM_HINTS if h in text)
    if pn_hits >= 3:
        return True

    return False


# ----------------------------- 5. Recent obituary -----------------------------

OBIT_URL_KEYWORDS = [
    "/obituaries", "/obituary", "/obits", "/tributes", "/tribute",
    "/recent-obituaries", "/current-obituaries", "/in-memoriam", "/memorial",
]
OBIT_PATH_FALLBACKS = [
    "/obituaries", "/obituary", "/obits", "/tributes", "/recent-obituaries",
    "/current-obituaries", "/in-memoriam",
]

MONTH_NAMES = (
    r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|"
    r"Nov(?:ember)?|Dec(?:ember)?"
)
DATE_PATTERN_MONTH = re.compile(
    rf"({MONTH_NAMES})\s+(\d{{1,2}}),?\s+(20\d{{2}})",
    re.IGNORECASE,
)
DATE_PATTERN_ISO = re.compile(r"(20\d{2})-(\d{2})-(\d{2})")
DATE_PATTERN_META = re.compile(
    r'(?:datetime|datePublished|content)="(20\d{2}-\d{2}-\d{2})',
    re.IGNORECASE,
)
DATE_PATTERN_USA = re.compile(r"(\d{1,2})/(\d{1,2})/(20\d{2})")

MONTH_TO_NUM = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def parse_dates_from_html(html):
    """Extract all parseable dates from HTML, return list of date objects."""
    dates = []
    for m in DATE_PATTERN_META.finditer(html):
        try:
            dates.append(datetime.date.fromisoformat(m.group(1)))
        except Exception:
            pass
    for m in DATE_PATTERN_ISO.finditer(html):
        try:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            dates.append(datetime.date(y, mo, d))
        except Exception:
            pass
    for m in DATE_PATTERN_MONTH.finditer(html):
        mname = m.group(1)[:3].lower()
        day = int(m.group(2))
        year = int(m.group(3))
        mo = MONTH_TO_NUM.get(mname)
        if mo:
            try:
                dates.append(datetime.date(year, mo, day))
            except Exception:
                pass
    for m in DATE_PATTERN_USA.finditer(html):
        try:
            mo, d, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if 1 <= mo <= 12 and 1 <= d <= 31:
                dates.append(datetime.date(y, mo, d))
        except Exception:
            pass
    return dates


def check_recent_obituary(home_html, base_url):
    """Pass if the obituaries page contains at least one date in the last
    30 days."""
    obit_url = (
        find_internal_link(home_html, base_url, OBIT_URL_KEYWORDS)
        or find_internal_link_by_path(home_html, base_url, OBIT_PATH_FALLBACKS)
    )
    if not obit_url:
        # No obituaries page found from the homepage is not "no recent obituary": the page may be
        # behind a menu we cannot read. Couldn't check, never a No (Welton 2026-10-21).
        _note_unread(base_url, "no obituaries page found from the homepage")
        return {"pass": False, "last_obit": None, "obit_url": None}
    page_html, status, _ = fetch_page(obit_url, timeout=12)
    if not page_html or not status or status >= 400:
        return {"pass": False, "last_obit": None, "obit_url": obit_url}
    dates = parse_dates_from_html(page_html)
    today = datetime.date.today()
    valid = [d for d in dates if d <= today and d.year >= 2015]
    if not valid:
        # A TributeTech list is loaded in the browser, so the page itself carries no dates (Welton 2026-10-29: 10 of
        # 52 readable funeral home sites read "couldn't check" this way). Its cards come from one request.
        try:
            tt = site_reader.tributetech_newest(page_html, obit_url, HEADERS)
        except Exception as e:
            _note_unread(obit_url, "TributeTech list not read: %s" % str(e)[:60])
            tt = None
        if tt and tt["newest"]:
            valid = [d for d in [tt["newest"]] if d <= today and d.year >= 2015]
    if not valid:
        _note_unread(obit_url, "no dates readable on the page")
        return {"pass": False, "last_obit": None, "obit_url": obit_url}
    most_recent = max(valid)
    cutoff = today - datetime.timedelta(days=30)
    return {
        "pass": most_recent >= cutoff,
        "last_obit": most_recent.isoformat(),
        "obit_url": obit_url,
    }


# ----------------------------- 7. LocalBusiness schema -----------------------------

SCHEMA_TARGET_TYPES = [
    "LocalBusiness", "FuneralHome", "ProfessionalService",
    "EmergencyService", "MedicalBusiness", "MedicalOrganization",
    "Cemetery", "Crematorium",
]


def check_local_business_schema(html):
    """Look for application/ld+json blocks containing LocalBusiness or subtype."""
    pattern = re.compile(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        re.IGNORECASE | re.DOTALL,
    )
    for m in pattern.finditer(html):
        block = m.group(1)
        for t in SCHEMA_TARGET_TYPES:
            if f'"{t}"' in block or f"'{t}'" in block:
                return True
    return False


# ----------------------------- 8. Google reviews widget -----------------------------

REVIEWS_WIDGET_HINTS = [
    "elfsight.com", "elfsight-app",
    "trustindex.io", "trustindex",
    "sociablekit",
    "reviewsonmywebsite.com",
    "embedreviews", "embedsocial",
    "tagembed.com", "widget-tagembed",
    "shapo.io",
    "famewall",
    "google-reviews-widget", "googlereviewswidget",
    "g-reviews-widget",
    "widget.reviewsforce",
    "rwgmaps",
    "trustpulse",
    "reputationmanager", "reviewbuilder",
]


def check_google_reviews_widget(html):
    html_lower = html.lower()
    for h in REVIEWS_WIDGET_HINTS:
        if h in html_lower:
            return True
    return False


# ----------------------------- platform detection -----------------------------

# Funeral home website platforms. Detected via fingerprints in the HTML
# (URLs, script paths, meta generators, comment headers). Sales-call data
# point only; not graded.
PLATFORM_FINGERPRINTS = [
    ("FuneralOne", [
        "funeralone.com", "f1edge", "lifetributes-cdn",
        "lifetributes.funeralone", "f1connect",
    ]),
    ("Frazer", [
        "frazerconsultants.com", "frazerwebsites.com",
    ]),
    ("Tukios", [
        "tukios.com", "tukioswebsites",
    ]),
    ("CFS", [
        "cfsmemorial.com", "consolidatedfuneralservices.com",
        "tribute-archive-cdn", "cfs-memorial",
    ]),
    ("Gather", [
        "gather.com", "gather-cdn", "gather-static", "gathercast",
    ]),
    ("Batesville", [
        "batesvilletechnologysolutions.com", "messenger.batesville",
    ]),
    ("Tribute Archive", [
        "tributearchive.com",
    ]),
    ("Squarespace", [
        "squarespace.com", "static.squarespace.com",
    ]),
    ("WordPress", [
        "wp-content/", "wp-includes/", "/wp-json/",
    ]),
    ("Wix", [
        "wix.com", "wixstatic.com",
    ]),
]


def detect_platform(html):
    """Return platform name string, or 'Unknown' if no match."""
    if not html:
        return "Unknown"
    html_lower = html.lower()
    for name, fingerprints in PLATFORM_FINGERPRINTS:
        for fp in fingerprints:
            if fp in html_lower:
                return name
    return "Unknown"


# ----------------------------- grading -----------------------------


def grade_website(checks):
    """A=8/8, B=6-7, C=3-5, D=1-2, F=0. None values are excluded and the
    threshold is scaled proportionally."""
    real = [(k, v) for k, v in checks.items() if v is not None]
    if not real or len(real) * 2 < len(checks):
        return None   # too little measured to grade (most checks could not read their page)
    passed = sum(1 for _, v in real if v)
    total = len(real)
    scaled = round(passed * 8 / total)
    if scaled >= 8:
        return "A"
    if scaled >= 6:
        return "B"
    if scaled >= 3:
        return "C"
    if scaled >= 1:
        return "D"
    return "F"


# ----------------------------- main entry -----------------------------


def audit(url):
    if not url:
        return {
            "url": "",
            "error": "no url provided",
            "checks": {},
            "grade": "F",
        }

    html, status, final_url = fetch_page(url)
    if html is None:
        return {
            "url": url,
            "error": f"fetch failed: {final_url}",
            "checks": {},
            "grade": "F",
        }
    moved = site_reader.landed_elsewhere(url, final_url)
    if moved:
        # Before the error check: an address that lands on another site, even one that answers with an error, is
    # the finding. The address we have lands on another site (Welton 2026-10-29): another site is not theirs to audit, and
        # where it went is the finding ("is your website still at that address?").
        return {
            "url": final_url,
            "status": status,
            "error": "the address goes to another site",
            "checks": {},
            "grade": None,
            "unverified": True,
            "unverified_reason": site_reader.MOVED % (site_reader.site_name(url), moved),
            "moved_from": site_reader.site_name(url),
            "moved_to": moved,
        }

    if status and status >= 400:
        return {
            "url": url,
            "error": f"HTTP {status}",
            "checks": {},
            "grade": "F",
        }

    if readable_chars(html) < MIN_READABLE_CHARS:
        return {
            "url": final_url,
            "status": status,
            "error": "site loads its content in the browser",
            "checks": {},
            "grade": None,
            "unverified": True,
            "unverified_reason": SCRIPT_BUILT_REASON,
        }

    base_url = base_origin(final_url)
    api_key = get_google_api_key()

    with ThreadPoolExecutor(max_workers=5) as ex:
        psi_future = ex.submit(check_pagespeed, final_url, api_key)
        family_future = ex.submit(measured, check_family_owner_story, html, base_url)
        preneed_future = ex.submit(measured, check_preneed_form, html, base_url)
        obit_future = ex.submit(measured, check_recent_obituary, html, base_url)

        psi = psi_future.result()
        family_pass = family_future.result()
        preneed_pass = preneed_future.result()
        obit = obit_future.result()

    checks = {
        "real_photos": check_real_photos(html),
        "pagespeed_mobile": psi.get("pass"),
        "family_owner_story": family_pass,
        "preneed_form": preneed_pass,
        "localbusiness_schema": check_local_business_schema(html),
        "google_reviews_widget": check_google_reviews_widget(html),
        "recent_obituary": obit.get("pass"),
    }

    return {
        "url": final_url,
        "status": status,
        "checks": checks,
        "pagespeed_score": psi.get("score"),
        "pagespeed_low": psi.get("low"),
        "pagespeed_high": psi.get("high"),
        "pagespeed_runs": psi.get("scores"),
        "pagespeed_error": psi.get("error"),
        "last_obituary": obit.get("last_obit"),
        "obit_url": obit.get("obit_url"),
        "platform": detect_platform(html),
        "grade": grade_website(checks),
    }


def main():
    parser = argparse.ArgumentParser(description="Funeral home website audit (hard mode)")
    parser.add_argument("--url", required=True)
    args = parser.parse_args()
    print(json.dumps(audit(args.url), indent=2))


if __name__ == "__main__":
    main()
