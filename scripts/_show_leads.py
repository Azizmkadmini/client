import csv
with open('leads/scraper_output.csv', encoding='utf-8') as f:
    rows = list(csv.DictReader(f))

print(f"{len(rows)} leads dans le CSV\n")
has_email = 0
has_wa = 0
for i, r in enumerate(rows, 1):
    email   = r.get('email', '').strip()
    wa      = r.get('whatsapp', '').strip()
    name    = r.get('name', '').strip() or '(sans nom)'
    company = r.get('company', '').strip() or '(sans entreprise)'
    poste   = r.get('poste', r.get('title', '')).strip()
    e_ok = email and email not in ('vide', '')
    w_ok = wa and wa not in ('vide', '')
    if e_ok: has_email += 1
    if w_ok: has_wa += 1
    print(f"{i}. {name} — {company}")
    if poste:   print(f"   Poste : {poste}")
    print(f"   Email : {email if e_ok else '—'}")
    print(f"   WA    : {wa if w_ok else '—'}")
    print()

print(f"Avec email    : {has_email}")
print(f"Avec WhatsApp : {has_wa}")
print(f"Sans contact  : {len(rows) - has_email - has_wa}")
