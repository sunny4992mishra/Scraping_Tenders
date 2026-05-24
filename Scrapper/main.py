import subprocess
import sys
 
SCRAPERS = [
   
    "CPPP_SCRAPER.PY",
    "kpp_Scrapper.py",
    "Telangana_scrapper.py"
    
]
 
for script in SCRAPERS:
    print(f"\n[*] Running {script}...")
    try:
        result = subprocess.run([sys.executable, script], check=False)
        if result.returncode != 0:
            print(f"[!] {script} exited with code {result.returncode}")
        else:
            print(f"[✓] Done: {script}")
    except Exception as e:
        print(f"[!] {script} failed to start: {e}")
 
print("\n[*] All scrapers finished.")
 