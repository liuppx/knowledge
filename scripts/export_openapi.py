from __future__ import annotations

from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from knowledge.api.openapi import SPEC_PATH, write_openapi_spec  # noqa: E402


def main() -> None:
    path_count, schema_count = write_openapi_spec()
    print(
        f"wrote {SPEC_PATH.relative_to(REPO_ROOT)} "
        f"({path_count} paths, {schema_count} schemas)"
    )


if __name__ == "__main__":
    main()
