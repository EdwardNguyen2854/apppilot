import json
import sys
import time
from http.server import HTTPServer, BaseHTTPRequestHandler


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "ok",
                "app": "dummy-api"
            }).encode())
        elif self.path == '/api/status':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                "uptime": int(time.time() - start_time),
                "requests": request_count
            }).encode())
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not found")

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({"received": True, "size": len(body)}).encode())

    def log_message(self, format, *args):
        global request_count
        request_count += 1
        sys.stderr.write("[%s] %s - %s\n" % (self.log_date_time_string(), self.client_address[0], format % args))


start_time = time.time()
request_count = 0

if __name__ == '__main__':
    port = 8789
    for i, arg in enumerate(sys.argv):
        if arg == '--port' and i + 1 < len(sys.argv):
            port = int(sys.argv[i + 1])

    server = HTTPServer(('127.0.0.1', port), Handler)
    sys.stderr.write(f"dummy-api: listening on port {port}\n")
    sys.stderr.flush()
    server.serve_forever()
