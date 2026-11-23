import os
import sys
import json
import subprocess
import time

# Ensure output is UTF-8 encoded
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

def run_step(command_list, step_name):
    print(f"\n=======================================================")
    print(f"🚀 RUNNING STEP: {step_name}")
    print(f"Command: {' '.join(command_list)}")
    print(f"=======================================================\n")
    start_time = time.time()
    
    try:
        result = subprocess.run(command_list, check=True, text=True)
        elapsed = time.time() - start_time
        print(f"\n[✔] SUCCESS: {step_name} completed in {elapsed:.2f}s.\n")
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n[❌] ERROR: {step_name} failed with exit code {e.returncode}.\n")
        return False
    except Exception as e:
        print(f"\n[❌] EXCEPTION: {step_name} failed due to: {e}\n")
        return False

def main():
    print("=== STARTING INTEGRATED VLXX SCRAPER WORKFLOW ===")
    start_all = time.time()
    
    # Step 1: Scrape video metadata and save to data.txt & Google Sheets
    # Runs the original scrape_videos.py in the root
    step1_ok = run_step([sys.executable, "scrape_videos.py"], "Scrape Video Metadata (scrape_videos.py)")
    
    if not step1_ok:
        print("[!] Warning: Step 1 failed or had errors. Proceeding to resolve stream links anyway...")
    
    # Step 2: Extract and resolve direct video stream sources
    # Runs the newly created scrape_all_links.py in scripts/
    step2_ok = run_step([sys.executable, "scripts/scrape_all_links.py"], "Resolve Video Stream Links (scripts/scrape_all_links.py)")
    
    elapsed_all = time.time() - start_all
    print("\n=======================================================")
    print("🏁 WORKFLOW COMPLETE")
    print(f"Total time elapsed: {elapsed_all:.2f}s")
    print(f"Step 1 (Metadata Scrape) Status: {'SUCCESS' if step1_ok else 'FAILED'}")
    print(f"Step 2 (Stream Link Resolve) Status: {'SUCCESS' if step2_ok else 'FAILED'}")
    print("=======================================================\n")

if __name__ == "__main__":
    main()
