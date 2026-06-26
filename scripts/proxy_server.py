import os
import sys
import re
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote
from curl_cffi import requests

# Force UTF-8 encoding for Windows terminals
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

PORT = 8899
session = requests.Session()

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://vlxx.moi/'
}

class VLXXDecryptionProxy(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress default HTTP logging to keep console clean
        pass

    def do_GET(self):
        parsed_path = urlparse(self.path)
        
        # 1. Health check / Root info
        if parsed_path.path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(b"<h3>VLXX Decrypting Proxy Server is Active!</h3><p>Use /m3u8?url=... to stream or download.</p>")
            return

        # 2. Serve the decrypted M3U8 Playlist
        if parsed_path.path in ['/m3u8', '/playlist.m3u8']:
            query = parse_qs(parsed_path.query)
            target_url = query.get('url', [None])[0]
            if not target_url:
                self.send_error(400, "Missing 'url' parameter")
                return
            
            target_url = unquote(target_url)
            print(f"[*] Fetching and decrypting playlist: {target_url}")
            
            try:
                r = session.get(target_url, headers=headers, impersonate="chrome120", timeout=15)
                if r.status_code != 200:
                    self.send_error(r.status_code, "Failed to fetch playlist from remote server")
                    return
                
                playlist_content = r.text
                
                # We need to rewrite all segment URLs in the playlist to go through our proxy
                lines = playlist_content.splitlines()
                rewritten_lines = []
                
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    if line.startswith('#'):
                        # Keep HLS tags as they are, but clean any unwanted tags if needed
                        if "EXT-X-KEY" in line:
                            # If there's encryption, keep it, but normally these are just raw ts inside png
                            pass
                        rewritten_lines.append(line)
                    else:
                        # This is a segment URL, route it through our proxy /segment
                        segment_proxy_url = f"http://127.0.0.1:{PORT}/segment?url={requests.utils.quote(line)}"
                        rewritten_lines.append(segment_proxy_url)
                
                decrypted_playlist = "\n".join(rewritten_lines)
                
                self.send_response(200)
                self.send_header('Content-Type', 'application/vnd.apple.mpegurl')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(decrypted_playlist.encode('utf-8'))
                
            except Exception as e:
                self.send_error(500, f"Error: {e}")
            return

        # 3. Serve the decrypted TS Segment (Strip PNG Header)
        if parsed_path.path == '/segment':
            query = parse_qs(parsed_path.query)
            segment_url = query.get('url', [None])[0]
            if not segment_url:
                self.send_error(400, "Missing segment 'url' parameter")
                return
            
            segment_url = unquote(segment_url)
            
            try:
                # Fetch the fake PNG segment
                r = session.get(segment_url, headers=headers, impersonate="chrome120", timeout=15)
                if r.status_code != 200:
                    self.send_error(r.status_code, "Failed to fetch segment")
                    return
                
                data = r.content
                
                # Check if it has a PNG signature
                # PNG signature is 89 50 4E 47 0D 0A 1A 0A
                has_png_sig = data.startswith(b'\x89PNG\r\n\x1a\n')
                
                if has_png_sig:
                    # Find the IEND chunk signature: 'IEND' (49 45 4E 44)
                    # The IEND chunk ends with 4 bytes of CRC after the 'IEND' signature,
                    # making the total IEND chunk size 12 bytes: [Length: 4 bytes (00 00 00 00)] [Type: 4 bytes (IEND)] [CRC: 4 bytes (AE 42 60 44)]
                    # In this target player, the index of HLS sync byte '0x47' is exactly at: data.find(b'IEND') + 8.
                    # Let's dynamically locate 'IEND' and add 8 bytes to get the start of the TS payload.
                    iend_idx = data.find(b'IEND')
                    if iend_idx != -1:
                        ts_start = iend_idx + 8
                        decrypted_data = data[ts_start:]
                    else:
                        # Fallback if IEND not found but has PNG signature
                        decrypted_data = data[95:]
                else:
                    # If it's already a raw TS segment (no PNG wrapper), pass it through untouched
                    decrypted_data = data
                
                # Send the clean TS segment back to VLC/FFmpeg
                self.send_response(200)
                self.send_header('Content-Type', 'video/mp2t')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Content-Length', str(len(decrypted_data)))
                self.end_headers()
                self.wfile.write(decrypted_data)
                
            except Exception as e:
                self.send_error(500, f"Error processing segment: {e}")
            return

        # Path not found
        self.send_error(404, "Path not found")

def run_server():
    server_address = ('', PORT)
    httpd = HTTPServer(server_address, VLXXDecryptionProxy)
    print(f"\n==================================================================")
    print(f"   [SUCCESS] VLXX DECRYPTING PROXY SERVER IS RUNNING ON PORT {PORT}")
    print(f"   - Local M3U8 Proxy: http://127.0.0.1:{PORT}/m3u8?url=[VL_STREAM_URL]")
    print(f"   - Keep this window open to stream or download using VLC / FFmpeg!")
    print(f"==================================================================\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Shutting down proxy server...")
        httpd.server_close()

if __name__ == '__main__':
    run_server()
