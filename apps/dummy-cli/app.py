import sys
import time

print("=== Dummy CLI App ===")
print(f"Arguments received: {sys.argv[1:] if len(sys.argv) > 1 else '(none)'}")
print("Processing...")
sys.stdout.flush()

time.sleep(1)

print("Step 1/3 complete")
sys.stdout.flush()
time.sleep(1)

print("Step 2/3 complete")
sys.stdout.flush()
time.sleep(1)

print("Step 3/3 complete")
print("Done - exiting with code 0")
sys.stdout.flush()
sys.exit(0)
