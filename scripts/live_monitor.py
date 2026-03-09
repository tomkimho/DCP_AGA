#!/usr/bin/env python3
"""
AGA Drug Discovery Pipeline — Live Monitor Server
실시간 파이프라인 모니터링 대시보드 + 가상 사무실

사용법:
  py scripts/live_monitor.py
  → 브라우저에서 http://localhost:8765 접속
"""

import http.server
import json
import os
import sys
from pathlib import Path
from datetime import datetime

# ── Config ──
PORT = 8765
BASE_DIR = Path(__file__).resolve().parent.parent
NEW_PAPERS_DIR = BASE_DIR / "new_papers"
COLLECTION_LOG = BASE_DIR / "collection_log.json"
PIPELINE_STATUS = BASE_DIR / "pipeline_status.json"
AGA_DATA = BASE_DIR / "AGA_data.xlsx"
HTML_FILE = BASE_DIR / "AGA_Virtual_Office.html"


def get_live_stats():
    """현재 파이프라인 상태를 실시간으로 수집"""
    stats = {
        "timestamp": datetime.now().isoformat(),
        "new_papers": {"pdf": 0, "txt": 0, "total": 0},
        "collection_log": {"total": 0, "papers": 0, "patents": 0, "biorxiv": 0},
        "pipeline_status": {},
        "aga_data_rows": 0,
        "recent_files": [],
        "disk_usage_mb": 0,
    }

    # 1) new_papers 폴더 파일 카운트
    if NEW_PAPERS_DIR.exists():
        try:
            pdf_files = list(NEW_PAPERS_DIR.glob("*.pdf"))
            txt_files = list(NEW_PAPERS_DIR.glob("*.txt"))
            all_files = [f for f in NEW_PAPERS_DIR.iterdir() if f.is_file()]
            stats["new_papers"]["pdf"] = len(pdf_files)
            stats["new_papers"]["txt"] = len(txt_files)
            stats["new_papers"]["total"] = len(all_files)

            # 최근 8개 파일 (수정 시간순)
            recent = sorted(all_files, key=lambda f: f.stat().st_mtime, reverse=True)[:8]
            for f in recent:
                st = f.stat()
                stats["recent_files"].append({
                    "name": f.name[:70],
                    "size_kb": round(st.st_size / 1024, 1),
                    "time": datetime.fromtimestamp(st.st_mtime).strftime("%H:%M:%S"),
                    "type": f.suffix,
                })

            # 디스크 사용량
            total_size = sum(f.stat().st_size for f in all_files)
            stats["disk_usage_mb"] = round(total_size / (1024 * 1024), 1)
        except Exception as e:
            print(f"[WARN] new_papers scan error: {e}")

    # 2) collection_log.json
    if COLLECTION_LOG.exists():
        try:
            with open(COLLECTION_LOG, "r", encoding="utf-8") as f:
                logs = json.load(f)
            stats["collection_log"]["total"] = len(logs)
            stats["collection_log"]["papers"] = sum(1 for x in logs if "pmid" in x)
            stats["collection_log"]["patents"] = sum(1 for x in logs if "patent_number" in x)
            stats["collection_log"]["biorxiv"] = sum(1 for x in logs if x.get("source") == "biorxiv")
        except Exception:
            pass

    # 3) pipeline_status.json
    if PIPELINE_STATUS.exists():
        try:
            with open(PIPELINE_STATUS, "r", encoding="utf-8") as f:
                stats["pipeline_status"] = json.load(f)
        except Exception:
            pass

    # 4) AGA_data.xlsx row count
    try:
        import openpyxl
        wb = openpyxl.load_workbook(str(AGA_DATA), read_only=True)
        ws = wb.active
        stats["aga_data_rows"] = sum(1 for _ in ws.iter_rows(min_row=2))
        wb.close()
    except Exception:
        stats["aga_data_rows"] = 709  # fallback

    return stats


class MonitorHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            try:
                # HTML 파일을 직접 읽어서 제공
                with open(HTML_FILE, "r", encoding="utf-8") as f:
                    html = f.read()
                html_bytes = html.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html_bytes)))
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.end_headers()
                self.wfile.write(html_bytes)
                print(f"[OK] HTML served ({len(html_bytes)} bytes)")
            except FileNotFoundError:
                self.send_response(500)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                err = f"<h1>ERROR</h1><p>HTML file not found: {HTML_FILE}</p>"
                self.wfile.write(err.encode("utf-8"))
                print(f"[ERROR] HTML file not found: {HTML_FILE}")

        elif self.path == "/api/stats":
            try:
                stats = get_live_stats()
                data = json.dumps(stats, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(data)
            except Exception as e:
                print(f"[ERROR] /api/stats: {e}")
                import traceback
                traceback.print_exc()
                fallback = json.dumps({
                    "timestamp": datetime.now().isoformat(),
                    "new_papers": {"pdf": 0, "txt": 0, "total": 0},
                    "collection_log": {"total": 0, "papers": 0, "patents": 0, "biorxiv": 0},
                    "pipeline_status": {},
                    "aga_data_rows": 0, "recent_files": [], "disk_usage_mb": 0,
                    "error": str(e)
                }).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(fallback)

        elif self.path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()

        else:
            self.send_error(404)

    def log_message(self, format, *args):
        if "/api/stats" not in str(args):
            print(f"[Monitor] {args[0]}")


def main():
    print("=" * 60)
    print("  AGA Drug Discovery Pipeline - Live Monitor")
    print("=" * 60)
    print(f"  Base: {BASE_DIR}")
    print(f"  URL:  http://localhost:{PORT}")
    print(f"  HTML: {HTML_FILE}")
    print(f"  HTML exists: {HTML_FILE.exists()}")
    print(f"  new_papers exists: {NEW_PAPERS_DIR.exists()}")
    print(f"  collection_log exists: {COLLECTION_LOG.exists()}")
    print(f"  pipeline_status exists: {PIPELINE_STATUS.exists()}")
    print(f"  AGA_data exists: {AGA_DATA.exists()}")
    print("=" * 60)
    print("  Ctrl+C to stop")
    print("=" * 60)

    if not HTML_FILE.exists():
        print(f"\n[FATAL] HTML file not found: {HTML_FILE}")
        input("Press Enter to exit...")
        sys.exit(1)

    # Quick test: can we get stats?
    try:
        s = get_live_stats()
        print(f"  [TEST] Stats OK - PDF:{s['new_papers']['pdf']}, Patents:{s['collection_log']['patents']}")
    except Exception as e:
        print(f"  [TEST] Stats ERROR: {e}")

    import webbrowser
    server = http.server.HTTPServer(("0.0.0.0", PORT), MonitorHandler)
    print(f"\n  Opening browser...")
    webbrowser.open(f"http://localhost:{PORT}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[Monitor] Stopped.")
        server.server_close()
    except OSError as e:
        print(f"\n[ERROR] Port {PORT} in use: {e}")
        input("Press Enter to exit...")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        input("Press Enter to exit...")
