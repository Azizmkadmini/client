import json
from pathlib import Path

log = Path('logs/sent.jsonl')
if not log.exists():
    print("Pas de logs/sent.jsonl")
    exit()

lines = log.read_text(encoding='utf-8').strip().splitlines()
last = lines[-10:] if len(lines) >= 10 else lines
print(f"Derniers {len(last)} envois :\n")
for line in last:
    try:
        r = json.loads(line)
        ts      = r.get('timestamp', r.get('ts', ''))[:19]
        subject = r.get('subject', '(pas de sujet)')
        preview = r.get('preview', r.get('message', ''))[:80]
        print(f"  [{ts}]")
        print(f"  Sujet   : {subject}")
        print(f"  Preview : {preview}...")
        print()
    except Exception as e:
        print(f"  Ligne invalide: {e}")
