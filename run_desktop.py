"""Windowed entry point used by the standalone desktop build."""
import sys
from codex_sentinel.gui.app import main

if __name__ == "__main__":
    sys.exit(main(smoke_test="--smoke-test" in sys.argv))
