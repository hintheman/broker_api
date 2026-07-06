import os
import sys

def debug_environment():
    print("=== Environment Debug ===")
    print("PYTHONPATH =", os.getenv("PYTHONPATH"))
    print("PWD =", os.getcwd())
    print("Executable =", sys.executable)
    print("sys.path =")
    for p in sys.path:
        print(f"  - {p}")

    print("Selected env vars:")
    for key in sorted(os.environ):
        if key.startswith("SCHWAB_") or key in ("PYTHONPATH", "PATH", "VIRTUAL_ENV", "HOME", "USER"):
            print(f"  {key}={os.environ.get(key)}")
