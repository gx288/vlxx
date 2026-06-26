import os
import re
import json
import time
import sys
from urllib.parse import urljoin, urlparse, parse_qs, urlunparse
from curl_cffi import requests
from bs4 import BeautifulSoup
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# Force UTF-8 encoding for Windows terminals to prevent crashes
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Configuration
INPUT_FILE = "data.txt"  # Located in the root of the vlxx folder
OUTPUT_DIR = "data"
OUTPUT_JSON = "data/vlxx_database.json"
OUTPUT_JS = "data/vlxx_database.js"
MAX_WORKERS = 8  # Moderate threads to be fast but polite
DELAY_BETWEEN_REQUESTS = 0.2

ACTIVE_DOMAIN = "vlxx.moi"

file_lock = threading.Lock()

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': f'https://{ACTIVE_DOMAIN}/',
    'X-Requested-With': 'XMLHttpRequest',
    'Origin': f'https://{ACTIVE_DOMAIN}',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'same-origin',
    'Sec-Fetch-Dest': 'empty',
    'Accept': '*/*',
    'Accept-Language': 'vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7'
}

def normalize_url(url):
    if not url:
        return url
    try:
        parsed = urlparse(url)
        if parsed.netloc.endswith("vlxx.moi") or parsed.netloc.startswith("vlxx."):
            new_parsed = parsed._replace(netloc=ACTIVE_DOMAIN)
            return urlunparse(new_parsed)
    except Exception:
        pass
    return url

def check_link_status(url, referer, session):
    head_headers = {
        'User-Agent': headers['User-Agent'],
        'Referer': referer
    }
    try:
        res = session.head(url, headers=head_headers, impersonate="chrome120", timeout=8)
        if res.status_code in [200, 206, 302]:
            return "live"
        return f"die (status {res.status_code})"
    except Exception as e:
        return f"die (error: {str(e)[:50]})"

def get_link_durability(url):
    if not url or not url.startswith("http"):
        return "unknown"
    try:
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)
        if any(k in query_params for k in ["expires", "sign", "token", "ip", "ttl"]):
            return "temporary"
        if "qooglevideo.com" in parsed.netloc or "googlevideo.com" in parsed.netloc:
            return "permanent"
        return "stable"
    except Exception:
        return "unknown"

def load_existing_progress():
    if os.path.exists(OUTPUT_JSON):
        try:
            with open(OUTPUT_JSON, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return {item['source_url']: item for item in data}
        except Exception as e:
            print(f"[*] Warning: Could not parse existing output file ({e}). Starting fresh.")
    return {}

def save_progress(database):
    items_list = list(database.values())
    
    # Ensure directory exists
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    with file_lock:
        try:
            # Save JSON
            with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
                json.dump(items_list, f, ensure_ascii=False, indent=2)
                
            # Save JS for local HTML dashboard loading (bypassing CORS)
            with open(OUTPUT_JS, 'w', encoding='utf-8') as f:
                f.write("window.vlxx_data = ")
                json.dump(items_list, f, ensure_ascii=False, indent=2)
                f.write(";")
        except Exception as e:
            print(f"[!] Error saving database to file: {e}")

def resolve_server_link(page_url, srv_index, video_id, session):
    """AJAX call to resolve player embed and extract the direct video link."""
    ajax_url = f"https://{ACTIVE_DOMAIN}/ajax.php"
    payload = f"vlxx_server=1&id={video_id}&server={srv_index}"
    
    ajax_headers = headers.copy()
    ajax_headers['Content-Type'] = 'application/x-www-form-urlencoded; charset=UTF-8'
    ajax_headers['Referer'] = page_url
    
    try:
        # Step 1: Call AJAX to get player iframe HTML
        res = session.post(ajax_url, data=payload, headers=ajax_headers, impersonate="chrome120", timeout=10)
        if res.status_code != 200:
            return None
            
        data = res.json()
        player_html = data.get("player", "")
        if not player_html:
            return None
            
        # Parse iframe src
        soup = BeautifulSoup(player_html, 'html.parser')
        iframe = soup.find('iframe')
        embed_url = iframe.get('src') if iframe else None
        
        if not embed_url:
            iframe_match = re.search(r'src=["\'](https?://[^"\']+)["\']', player_html)
            if iframe_match:
                embed_url = iframe_match.group(1)
                
        if embed_url:
            embed_url = urljoin(page_url, embed_url)
            
            # Step 2: Fetch embed page and parse direct URL from window.__SRC
            embed_headers = {
                'User-Agent': headers['User-Agent'],
                'Referer': page_url
            }
            embed_res = session.get(embed_url, headers=embed_headers, impersonate="chrome120", timeout=10)
            if embed_res.status_code == 200:
                html = embed_res.text
                match = re.search(r'window\.__SRC\s*=\s*(\[.*?\])\s*;', html)
                if match:
                    src_data = json.loads(match.group(1))
                    if src_data and len(src_data) > 0:
                        video_info = src_data[0]
                        direct_url = video_info.get("file")
                        v_type = video_info.get("type", "hls")
                        
                        if direct_url:
                            # Step 3: Check connectivity
                            status = check_link_status(direct_url, embed_url, session)
                            return {
                                "type": "hls" if v_type.lower() == "hls" or ".m3u8" in direct_url.lower() or ".vl" in direct_url.lower() else "mp4",
                                "url": direct_url,
                                "status": status,
                                "durability": get_link_durability(direct_url),
                                "embed_url": embed_url
                            }
    except Exception:
        pass
    return None

def scrape_video_page(page_url, session):
    """Scrape the detail page to find all server buttons and resolve them."""
    target_url = normalize_url(page_url)
    
    page_headers = headers.copy()
    page_headers['Referer'] = f"https://{ACTIVE_DOMAIN}/"
    
    r = session.get(target_url, headers=page_headers, impersonate="chrome120", timeout=12)
    if r.status_code != 200:
        return None
        
    soup = BeautifulSoup(r.text, 'html.parser')
    
    # Find all server items in <ul class="video-servers">
    servers_list = soup.find('ul', class_='video-servers')
    if not servers_list:
        return None
        
    items = servers_list.find_all('li', class_='video-server')
    if not items:
        return None
        
    result = {"servers": {}}
    
    for item in items:
        srv_name = item.get_text().strip()
        if not srv_name.startswith("#"):
            srv_name = f"Server {srv_name}"
            
        onclick = item.get('onclick', '')
        # Pattern like: server(1,3172)
        match = re.search(r'server\((\d+)\s*,\s*(\d+)\)', onclick)
        if not match:
            continue
            
        srv_index = match.group(1)
        video_id = match.group(2)
        
        # Resolve the link for this server
        resolved = resolve_server_link(target_url, srv_index, video_id, session)
        if resolved:
            result["servers"][srv_name] = resolved
            
    return result if result["servers"] else None

def process_single_video(item, scraped_db):
    original_url = item.get('link')
    if not original_url or original_url == 'N/A':
        return None
        
    normalized_page_url = normalize_url(original_url)
    if normalized_page_url in scraped_db:
        return None
        
    thread_session = requests.Session()
    try:
        scraped_data = scrape_video_page(normalized_page_url, thread_session)
        if scraped_data:
            # Format views and likes
            views = item.get('views', 0)
            likes = item.get('likes', 0)
            dislikes = item.get('dislikes', 0)
            
            video_record = {
                "id": str(item.get('id')),
                "title": item.get('title'),
                "source_url": normalized_page_url,
                "thumbnail": item.get('thumbnail'),
                "ribbon": item.get('ribbon', ''),
                "views": int(views) if views else 0,
                "likes": int(likes) if likes else 0,
                "dislikes": int(dislikes) if dislikes else 0,
                "rating": item.get('rating', 0),
                "video_code": item.get('video_code', ''),
                "description": item.get('description', ''),
                "actress": item.get('actress', ''),
                "date": item.get('date'), # Preserve publish date if present!
                "extracted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "servers": scraped_data["servers"]
            }
            return normalized_page_url, video_record
    except Exception as e:
        print(f"    [!] Error on {item.get('title')[:30]}: {e}")
    return None

def main():
    print("=== VLXX OFFLINE HIGH-SPEED MULTI-THREADED SCRAPER ===")
    print(f"[*] Configuration: Thread Workers = {MAX_WORKERS}")
    print(f"[*] Normalizing all domains to: {ACTIVE_DOMAIN}")
    
    if not os.path.exists(INPUT_FILE):
        print(f"[!] Error: Input file '{INPUT_FILE}' not found. Run this script in the root of the vlxx repo.")
        return
        
    print(f"[*] Loading '{INPUT_FILE}'...")
    try:
        with open(INPUT_FILE, 'r', encoding='utf-8') as f:
            raw_videos = json.load(f)
    except Exception as e:
        print(f"[!] Failed to parse {INPUT_FILE}: {e}")
        return
        
    total_videos = len(raw_videos)
    print(f"[+] Loaded {total_videos} videos from {INPUT_FILE}.")
    
    scraped_db = load_existing_progress()
    scraped_count = len(scraped_db)
    print(f"[*] Checkpoint loaded: {scraped_count} / {total_videos} videos already scraped.")
    
    if scraped_count > 0:
        save_progress(scraped_db)
        print("[*] Synchronized local database files (.json & .js) successfully.")
        
    videos_to_scrape = []
    for item in raw_videos:
        norm_url = normalize_url(item.get('link'))
        if norm_url and norm_url not in scraped_db:
            videos_to_scrape.append(item)
            
    remaining_count = len(videos_to_scrape)
    print(f"[*] Remaining videos to scrape: {remaining_count}")
    
    if remaining_count == 0:
        print("[🎉 SUCCESS] All videos have already been scraped!")
        return
        
    print("\n[*] Initializing thread pool. Starting parallel extraction...")
    start_time = time.time()
    success_in_session = 0
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_single_video, item, scraped_db): item for item in videos_to_scrape}
        
        for future in as_completed(futures):
            res = future.result()
            if res:
                page_url, record = res
                scraped_db[page_url] = record
                success_in_session += 1
                
                # Dynamic terminal logging
                total_scraped = len(scraped_db)
                pct = (total_scraped / total_videos) * 100
                
                # Print server log preview
                server_logs = []
                for srv_name, srv in record["servers"].items():
                    server_logs.append(f"\n    - {srv_name}: {srv['status']} -> {srv['url'][:60]}...")
                
                print(f"[{total_scraped}/{total_videos}] ({pct:.2f}%) Extracted: {record['title'][:50]}...{''.join(server_logs)}")
                
                # Autosave checkpoints every 10 successful scrapes
                if success_in_session % 10 == 0:
                    save_progress(scraped_db)
                    
            time.sleep(DELAY_BETWEEN_REQUESTS)
            
    # Final save
    save_progress(scraped_db)
    elapsed = time.time() - start_time
    print("\n=== SCRAPE PROCESS COMPLETED ===")
    print(f"[+] Total items in database: {len(scraped_db)}")
    print(f"[+] Newly scraped this session: {success_in_session}")
    print(f"[+] Total time elapsed: {elapsed:.1f} seconds.")
    print("[*] Open your dashboard to view statistics and links!")

if __name__ == "__main__":
    main()
