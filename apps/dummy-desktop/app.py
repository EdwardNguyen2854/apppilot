import sys
import time
import os

app_id = os.environ.get('APPPILOT_APP_ID', 'dummy-desktop')
sys.stderr.write(f"{app_id}: started (PID {os.getpid()})\n")
sys.stderr.flush()

try:
    counter = 0
    while True:
        time.sleep(5)
        counter += 1
        sys.stderr.write(f"{app_id}: heartbeat {counter}\n")
        sys.stderr.flush()
except KeyboardInterrupt:
    sys.stderr.write(f"{app_id}: shutting down\n")
    sys.stderr.flush()
    sys.exit(0)
