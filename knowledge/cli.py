from __future__ import annotations

import argparse
from collections.abc import Sequence

import uvicorn


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the Knowledge development server.")
    parser.add_argument("--host", default="127.0.0.1", help="interface to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8002, help="port to bind (default: 8002)")
    parser.add_argument(
        "--reload",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="enable or disable automatic reload (enabled by default)",
    )
    args = parser.parse_args(argv)

    uvicorn.run(
        "knowledge.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
