# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.
"""Bind a native read_file result to facts explicitly registered by the host."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class EvidenceFact(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    subject: str = Field(min_length=1)
    property: str = Field(min_length=1)
    version: str = Field(min_length=1)
    scope: str | None = None
    adjudicates: bool = False


class EvidenceFile(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    result_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    facts: list[EvidenceFact] = Field(min_length=1)


class FileEvidenceAdapter:
    def __init__(self, files: dict[str, EvidenceFile]):
        self.files = {}
        for name, entry in files.items():
            path = Path(name)
            if not path.is_absolute() or ".." in path.parts or path in self.files:
                raise ValueError("evidence_files requires unique absolute paths without parent traversal")
            self.files[path] = entry

    def extract(self, tool_call, result, message):
        from openjiuwen.core.foundation.tool.schema import ToolOutput
        from openjiuwen.core.single_agent.runtime_monitor import Observation, ToolEvidence

        fallback = ToolEvidence(observations=[Observation(text=str(message.content))])
        if tool_call.name != "read_file" or not isinstance(result, ToolOutput) or not result.success:
            return fallback
        data = result.data
        if not isinstance(data, dict) or not isinstance(data.get("file_path"), str):
            return fallback
        path = Path(data["file_path"])
        entry = self.files.get(path)
        content = data.get("content")
        if entry is None or not isinstance(content, str) or not content:
            return fallback
        args = tool_call.arguments
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except ValueError:
                return fallback
        if not isinstance(args, dict) or args.get("offset", 0) != 0 or args.get("limit") is not None or args.get("pages"):
            return fallback
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if digest != entry.result_sha256:
            return fallback
        return ToolEvidence(observations=[
            Observation(
                text=content, source=str(path), subject=fact.subject, property=fact.property,
                version=fact.version, scope=fact.scope,
                resolution_ref=f"sha256:{digest}" if fact.adjudicates else None,
            ) for fact in entry.facts
        ])
