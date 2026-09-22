"""Fail closed on unlisted release files and common accidental secret material.

This bounded guard supplements human review; it is not a complete secret scanner.
It prints paths and rule names only, never matched content or credentials.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
from zipfile import ZipFile


RULES = {
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "github_token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{30,})\b"),
    "model_api_key": re.compile(r"\bsk-(?:proj-|ant-)?[A-Za-z0-9_-]{24,}\b"),
    "jwt": re.compile(r"\beyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\b"),
    "private_profile_path": re.compile(r'''(?:[A-Za-z]:[\\/]+Users[\\/]+[^\s/'"\\]+|/(?:Users|home)/[^\s/'"]+)''', re.I),
    "private_chat_link": re.compile(r"(?:chatgpt-conversation://|https://chatgpt\.com/c/)[A-Za-z0-9-]+"),
    "credential_value": re.compile(r'''["'](?:access_token|refresh_token|id_token|OPENAI_API_KEY)["']\s*:\s*["'][^"'\s]{12,}["']'''),
}

PRIVATE_COMPONENTS = {
    ".git", ".codex", ".ssh", ".aws", ".azure", ".venv", "node_modules",
    "private-data", "private-reports", "private-benchmarks", "runtime-data", ".publish",
}


def scan_text(text: str) -> list[str]:
    return [name for name, rule in RULES.items() if rule.search(text)]


def read_allowlist(root: Path) -> list[str]:
    data = json.loads((root / ".release-files.json").read_text(encoding="utf-8"))
    paths = data["files"]
    if not isinstance(paths, list) or len(paths) != len(set(paths)):
        raise ValueError("Release allowlist must have unique paths")
    for value in paths:
        if not isinstance(value, str):
            raise ValueError("Release paths must be strings")
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or "\\" in value or ":" in value:
            raise ValueError("Release paths must be relative POSIX paths")
        if (set(path.parts) & PRIVATE_COMPONENTS or path.name in {".env", "auth.json", "credentials.json"}
                or path.suffix.lower() in {".key", ".pem", ".p12", ".pfx", ".sqlite", ".sqlite3", ".db"}):
            raise ValueError("A private path was included in the release allowlist")
    return paths


def check(root: Path, *, tracked: bool = False) -> dict:
    root = root.resolve()
    paths = read_allowlist(root)
    findings = []
    if tracked:
        output = subprocess.check_output(["git", "ls-files", "-z"], cwd=root)
        actual = set(output.decode("utf-8").rstrip("\0").split("\0")) - {""}
        if actual != set(paths):
            findings.append({"rule": "tracked_allowlist_mismatch", "extra": sorted(actual - set(paths)), "missing": sorted(set(paths) - actual)})
        if subprocess.run(["git", "diff", "--quiet"], cwd=root, check=False).returncode:
            findings.append({"rule": "unstaged_changes", "message": "Stage reviewed changes before checking the index."})
    for relative in paths:
        path = root / relative
        if path.is_symlink() or not path.resolve().is_relative_to(root) or not path.is_file():
            findings.append({"path": relative, "rule": "missing_or_unsafe_path"})
            continue
        if path.stat().st_size > 5_000_000:
            findings.append({"path": relative, "rule": "oversized_file"})
            continue
        if path.suffix == ".xlsx":
            with ZipFile(path) as archive:
                if sum(item.file_size for item in archive.infolist()) > 10_000_000:
                    findings.append({"path": relative, "rule": "oversized_workbook"})
                    continue
                contents = "\n".join(archive.read(name).decode("utf-8") for name in archive.namelist() if name.endswith(".xml"))
        elif path.suffix == ".png":
            # Visible image content is separately reviewed by a person/agent.
            contents = path.read_bytes().decode("latin-1")
        else:
            contents = path.read_text(encoding="utf-8")
        findings.extend({"path": relative, "rule": rule} for rule in scan_text(contents))
    return {"ok": not findings, "allowlisted_files": len(paths), "tracked_checked": tracked, "findings": findings}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--tracked", action="store_true", help="Require exact equality between the Git index and reviewed allowlist")
    args = parser.parse_args()
    result = check(args.root, tracked=args.tracked)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
