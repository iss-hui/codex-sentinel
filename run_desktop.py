import os
import sys

# Ensure stdout and stderr are valid streams in windowed mode
if sys.stdout is None:
    try:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    except Exception:
        pass
if sys.stderr is None:
    try:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    except Exception:
        pass

from codex_sentinel.gui.app import main

if __name__ == "__main__":
    sys.exit(main(smoke_test="--smoke-test" in sys.argv))
