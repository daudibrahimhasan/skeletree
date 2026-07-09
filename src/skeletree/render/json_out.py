"""JSON renderer — same model as Markdown, for tooling/programmatic consumers.

Includes the token-savings figures so a CI step or editor plugin can surface
them without recomputing.
"""

from __future__ import annotations

import json

from ..model import ProjectMap
from ..tokens import TokenSavings


def render(project: ProjectMap, savings: TokenSavings) -> str:
    payload = {
        "root_name": project.root_name,
        "description": project.description,
        "savings": {
            "map_tokens": savings.map_tokens,
            "baseline_tokens": savings.baseline_tokens,
            "saved_tokens": savings.saved_tokens,
            "percent_smaller": savings.percent_smaller,
            "file_count": savings.file_count,
        },
        "truncated": project.truncated,
        "deps": [d.to_dict() for d in project.deps],
        "files": [f.to_dict() for f in project.files],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
