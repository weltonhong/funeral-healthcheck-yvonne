# Funeral Home Online Health Check

Streamlit web app that runs a 60-90 second online presence audit on a
funeral home prospect at a trade show booth and produces a branded
one-page Ring Ring Marketing PDF scorecard.

This is the deployable slice of the
`tradeshow-healthcheck-funeralhome` skill from the internal Powerhouse
repo. It contains only the health check code -- no client data, no
other skills.

CTA routes to **Yvonne Reese** (Yvonne.Reese@RingRingMarketing.com).

## Run locally

```bash
cd my-skills/tradeshow-healthcheck-funeralhome/webapp
pip install -r requirements.txt

# On Mac/Linux:
export GOOGLE_API_KEY=...
export SCRAPINGBEE_API_KEY=...

# On Windows (PowerShell):
# $env:GOOGLE_API_KEY="..."
# $env:SCRAPINGBEE_API_KEY="..."

streamlit run app.py
```

Open <http://localhost:8501>.

## Deploy to Streamlit Cloud

1. Push this repo to GitHub (already done if you're reading this on GitHub).
2. Go to <https://share.streamlit.io> -> **Create app** -> **Deploy from GitHub**.
3. Settings:
   - **Repository:** `weltonhong/funeral-healthcheck-yvonne`
   - **Branch:** `main`
   - **Main file path:** `my-skills/tradeshow-healthcheck-funeralhome/webapp/app.py`
   - **Python version:** 3.12
4. Open **Advanced settings** -> **Secrets** and paste:
   ```toml
   GOOGLE_API_KEY = "AIzaSy..."
   SCRAPINGBEE_API_KEY = "..."
   ```
5. Click **Deploy**. First build takes 2-4 minutes.

Target URL: `funeral-healthcheck-yvonne.streamlit.app`

## What gets scanned

| Check | Source |
|-------|--------|
| Google Reviews | Google Places API |
| Google 3-Pack (per city + cremation in home city) | Google SERP via UULE |
| Google SEO (per city + cremation in home city) | ScrapingBee + UULE |
| Google Ads (per bucket) | Parsed from same SERP HTML |
| Website (8 funeral-vertical checks) | requests + PageSpeed Insights API |
| Reviews snapshot | Google + Facebook + Yelp |

Each check produces a letter grade. Overall grade is the average of the
graded checks; "Unable to verify" website audits are excluded.

## Search buckets

For every city the rep enters, we run **funeral home [city] [state]**.
For the home city only, we ALSO run **cremation [city] [state]** so the
report shows ranking for both at-need search intents.

## Funeral home website checks (8)

1. Real photos (no stock CDN, no generic alt text)
2. PageSpeed mobile score >= 50
3. Family/owner About page that names actual people
4. Pre-need / pre-arrangement contact form or page
5. LocalBusiness schema (FuneralHome subtype counts)
6. Google reviews widget
7. Recent obituary posted in the last 30 days
8. Livestream / tribute video offering

Platform is also detected (Frazer, Tukios, FuneralOne, CFS, Gather, etc.)
and surfaced as a sales-call data point. Platform is not graded.

## Repo layout

```
my-skills/
  tradeshow-healthcheck-funeralhome/
    SKILL.md
    scripts/
      health_check.py        # Orchestrator - runs all checks in parallel
      google_serp_rank.py    # Real Google SERP via ScrapingBee
      website_audit.py       # Funeral-vertical homepage scrape + heuristics
      pdf_generator.py       # Branded RRM one-page PDF + Calendly QR
      verify_qr.py           # Decodes generated QR to confirm Calendly URL
    webapp/
      app.py                 # Streamlit UI
      requirements.txt
      assets/
        rrm_logo.jpg
      README.md
  quick-intel/
    scripts/
      google_intel.py        # Google Places lookup (target + competitors)
```

## API keys you need

| Key | What it powers | Where to get it |
|-----|----------------|-----------------|
| `GOOGLE_API_KEY` | Google Places + Geocoding + PageSpeed Insights | Google Cloud Console |
| `SCRAPINGBEE_API_KEY` | Real Google SERP rendering | scrapingbee.com |

Both keys must be set in `os.environ` (locally) or in Streamlit Cloud
**Secrets** (deployed). The webapp mirrors `st.secrets` into `os.environ`
at startup so the underlying scripts pick them up.

## Calendly QR

The Calendly QR code on the bottom of the PDF is regenerated fresh on
every PDF build from `pdf_generator.CALENDLY_URL`. To swap reps later,
change that one constant -- no committed asset to re-export.

To verify the QR points where you expect:

```bash
python my-skills/tradeshow-healthcheck-funeralhome/scripts/verify_qr.py
```
