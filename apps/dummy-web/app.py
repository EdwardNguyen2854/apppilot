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
                "app": "dummy-web",
                "uptime": int(time.time() - start_time)
            }).encode())
        elif self.path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b"Dummy Web App is running")
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not found")

    def log_message(self, format, *args):
        sys.stderr.write("[%s] %s - %s\n" % (self.log_date_time_string(), self.client_address[0], format % args))


start_time = time.time()

if __name__ == '__main__':
    port = 8788
    for i, arg in enumerate(sys.argv):
        if arg == '--port' and i + 1 < len(sys.argv):
            port = int(sys.argv[i + 1])

    server = HTTPServer(('127.0.0.1', port), Handler)
    sys.stderr.write(f"dummy-web: listening on port {port}\n")
    sys.stderr.flush()
    server.serve_forever()
