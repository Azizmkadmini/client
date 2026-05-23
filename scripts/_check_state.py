import sqlite3, os, csv as csv_mod
from pathlib import Path

ROOT = Path(__file__).parent.parent

# Cache scraper
cache_db = ROOT / "data" / "scraper_cache.db"
if cache_db.exists():
    conn = sqlite3.connect(cache_db)
    total    = conn.execute("SELECT COUNT(*) FROM scraper_profile_cache").fetchone()[0]
    pending  = conn.execute("SELECT COUNT(*) FROM scraper_profile_cache WHERE has_email=1 AND (outreach_status IS NULL OR outreach_status='pending')").fetchone()[0]
    contacted= conn.execute("SELECT COUNT(*) FROM scraper_profile_cache WHERE outreach_status='contacted'").fetchone()[0]
    conn.close()
    print(f"Cache total     : {total} profils")
    print(f"Prets a envoyer : {pending} (email present, pas encore contactes)")
    print(f"Deja contactes  : {contacted}")
else:
    print("Cache vide — aucun scraping effectue")

# CSV scraper
csv_path = ROOT / "leads" / "scraper_output.csv"
if csv_path.exists():
    with open(csv_path, encoding="utf-8") as f:
        rows = list(csv_mod.DictReader(f))
    with_email = [r for r in rows if r.get("email","").strip() and r.get("email","").strip() not in ("vide","")]
    print(f"\nCSV scraper     : {len(rows)} profils dont {len(with_email)} avec email")
    if with_email:
        print("Exemples :")
        for r in with_email[:3]:
            print(f"  - {r.get('name','')} | {r.get('company','')} | {r.get('email','')}")
else:
    print("\nPas de CSV scraper — il faut lancer le scraping d'abord")

# LeadStore
app_db = ROOT / "data" / "app.db"
if app_db.exists():
    conn = sqlite3.connect(app_db)
    try:
        total_leads = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
        pending_leads = conn.execute("SELECT COUNT(*) FROM leads WHERE status='pending' AND channel='email'").fetchone()[0]
        print(f"\nLeadStore       : {total_leads} leads total, {pending_leads} en attente email")
    except Exception as e:
        print(f"\nLeadStore       : {e}")
    conn.close()
