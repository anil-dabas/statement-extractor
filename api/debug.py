from http.server import BaseHTTPRequestHandler
import json
import os
import sys

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        debug_info = {
            "cwd": os.getcwd(),
            "file_dir": os.path.dirname(os.path.abspath(__file__)),
            "sys_path": sys.path[:5],
        }

        # Try to check if backend exists
        backend_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend')
        debug_info["backend_path"] = backend_path
        debug_info["backend_exists"] = os.path.exists(backend_path)

        if os.path.exists(backend_path):
            try:
                debug_info["backend_contents"] = os.listdir(backend_path)
            except Exception as e:
                debug_info["backend_contents_error"] = str(e)

        # Try to import
        try:
            sys.path.insert(0, backend_path)
            from core.detector import BankDetector
            debug_info["import_success"] = True
        except Exception as e:
            debug_info["import_error"] = str(e)
            import traceback
            debug_info["traceback"] = traceback.format_exc()

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(debug_info, indent=2).encode())
