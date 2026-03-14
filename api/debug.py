from http.server import BaseHTTPRequestHandler
import json
import os
from pathlib import Path

TEMP_DIR = Path('/tmp/bank_statement_converter')

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        debug_info = {
            "temp_dir_exists": TEMP_DIR.exists(),
            "sessions": []
        }

        if TEMP_DIR.exists():
            for item in TEMP_DIR.iterdir():
                if item.is_dir():
                    session_info = {
                        "id": item.name,
                        "files": []
                    }
                    session_file = item / "session.json"
                    if session_file.exists():
                        session_info["has_session_json"] = True
                        try:
                            with open(session_file, 'r') as f:
                                data = json.load(f)
                                session_info["session_data"] = data
                        except Exception as e:
                            session_info["session_read_error"] = str(e)
                    else:
                        session_info["has_session_json"] = False

                    for f in item.iterdir():
                        if f.name != "session.json":
                            session_info["files"].append(f.name)

                    debug_info["sessions"].append(session_info)

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(debug_info, indent=2).encode())
