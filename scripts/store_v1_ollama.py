"""Start the existing Ollama component inside only the disposable chat runner."""
from __future__ import annotations

import os
import runpy
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx

from scripts.store_v1_playground import require_isolation


def main() -> None:
    if os.getenv("STORE_OLLAMA_CACHED_ONLY") == "true":
        db = urlparse(os.getenv("DATABASE_URL", ""))
        if (db.hostname, db.path) != ("database", "/hedge_store_workspace"):
            raise ValueError("Cached Store model mode requires the private workspace")
    else:
        require_isolation()
    binary = '/opt/ollama/bin/ollama'
    daemon = subprocess.Popen([binary, 'serve'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                httpx.get('http://127.0.0.1:11434/api/tags', timeout=1, trust_env=False).raise_for_status()
                break
            except httpx.HTTPError:
                if daemon.poll() is not None:
                    raise SystemExit('Isolated Ollama failed startup') from None
                time.sleep(0.2)
        else:
            raise SystemExit('Isolated Ollama startup timed out')
        model = os.environ['OLLAMA_MODEL']
        # Pull only the public configured model into this private developer cache.
        try:
            if os.getenv("STORE_OLLAMA_CACHED_ONLY") == "true":
                available = httpx.get('http://127.0.0.1:11434/api/tags', timeout=3, trust_env=False).json()
                if not any(m.get('name') == model for m in available.get('models', [])):
                    print('Cached model unavailable; replies will use deterministic fallback', file=sys.stderr)
            else:
                subprocess.run([binary, 'pull', model], check=True, timeout=600,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            print('Isolated model unavailable; replies will use deterministic fallback', file=sys.stderr)
        args = sys.argv[1:]
        if args[0] == '-m':
            sys.argv = [args[1], *args[2:]]
            runpy.run_module(args[1], run_name='__main__')
        else:
            sys.argv = args
            runpy.run_path(str(Path(args[0])), run_name='__main__')
    finally:
        daemon.terminate()
        try:
            daemon.wait(timeout=5)
        except subprocess.TimeoutExpired:
            daemon.kill()
            daemon.wait()


if __name__ == '__main__':
    main()
