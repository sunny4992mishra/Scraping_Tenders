
import subprocess
import sys
 
SCRAPERS = [
    "AP_scrapper.py",
    "CPPP_SCRAPER.PY",
    "kpp_Scrapper.py",
    "Telangana_scrapper.py",
    "unified_Scrapper.py",
]
 
for script in SCRAPERS:
    print(f"\n[*] Running {script}...")
    try:
        subprocess.run([sys.executable, script], check=False)
    except Exception as e:
        print(f"[!] {script} failed to start: {e}")
    print(f"[*] Done: {script}")
 
print("\n[*] All scrapers finished.")