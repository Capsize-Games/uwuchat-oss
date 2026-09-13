"""API-backed eval tests for the LLM agent via the Docker server.

These tests communicate with the running AI Runner API server
(Docker container) through WebSocket and HTTP endpoints rather
than starting a local daemon subprocess.

Usage (from host)::

    ./scripts/docker.sh test-eval
    ./scripts/docker.sh test-eval -v -k test_llm_retrieves

Usage (via run_tests.py)::

    python scripts/run_tests.py --eval --docker
    python scripts/run_tests.py --eval --docker --model qwen3.5-9b

Usage (inside the container)::

    python -m pytest server/tests/eval/ --timeout=600
"""
