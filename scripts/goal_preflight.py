"""Print a bounded, current checkout snapshot for Goal continuation."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    "AGENTS.md",
    "docs/operacao-goal.md",
    "docs/plano-produto-e-handoff.md",
    "docs/equipe-e-execucao.md",
    "docs/roadmap.md",
    "docs/validacao-real.md",
    "reports/estado-goal.md",
)


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(ROOT), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout.strip()


def changed_paths() -> list[str]:
    paths: set[str] = set()
    for args in (
        ("diff", "--name-only", "-z", "HEAD"),
        ("ls-files", "--others", "--exclude-standard", "-z"),
    ):
        result = subprocess.run(
            ["git", "-C", str(ROOT), *args],
            check=True,
            capture_output=True,
        )
        paths.update(result.stdout.decode("utf-8").strip("\0").split("\0"))
    paths.discard("")
    paths.discard("reports/estado-goal.md")
    return sorted(paths)


def worktree_fingerprint() -> str:
    digest = hashlib.sha256()
    for relative_path in changed_paths():
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\0")
        path = ROOT / relative_path
        if not path.is_file():
            digest.update(b"<deleted>")
            continue
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()[:12]


def main() -> int:
    missing = [path for path in REQUIRED if not (ROOT / path).is_file()]
    if missing:
        print(f"Arquivos obrigatórios ausentes: {', '.join(missing)}", file=sys.stderr)
        return 2

    try:
        top_level = Path(git("rev-parse", "--show-toplevel")).resolve()
        head = git("rev-parse", "--short", "HEAD")
        branch = git("branch", "--show-current")
        status = git("status", "--short")
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"Não foi possível verificar o checkout: {exc}", file=sys.stderr)
        return 2

    if top_level != ROOT:
        print(f"Checkout inesperado: {top_level}", file=sys.stderr)
        return 2

    state = (ROOT / "reports/estado-goal.md").read_text(encoding="utf-8")
    head_mark = re.search(r"^<!-- goal-head: ([0-9a-f]+) -->$", state, re.MULTILINE)
    item_mark = re.search(r"^<!-- goal-item: (P[0-5]) -->$", state, re.MULTILINE)
    tree_mark = re.search(r"^<!-- goal-tree: ([0-9a-f]{12}) -->$", state, re.MULTILINE)
    if head_mark is None or item_mark is None or tree_mark is None:
        print("Estado sem marcas goal-head, goal-item e goal-tree válidas.", file=sys.stderr)
        return 2

    item = item_mark.group(1)
    plan = (ROOT / "docs/plano-produto-e-handoff.md").read_text(encoding="utf-8")
    if not re.search(rf"^\| {item} \|", plan, re.MULTILINE):
        print(f"Item {item} ausente da fila P0–P5.", file=sys.stderr)
        return 2

    document_hashes = {
        path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()[:12]
        for path in REQUIRED
        if path != "reports/estado-goal.md"
    }
    try:
        tree = worktree_fingerprint()
    except (OSError, UnicodeError, subprocess.CalledProcessError) as exc:
        print(f"Não foi possível conferir a árvore de trabalho: {exc}", file=sys.stderr)
        return 2
    snapshot = {
        "repo": str(ROOT),
        "head": head,
        "state_head": head_mark.group(1),
        "worktree_fingerprint": tree,
        "state_tree": tree_mark.group(1),
        "branch": branch,
        "modified_or_untracked_entries": len(status.splitlines()) if status else 0,
        "active_item": item,
        "documents_sha256_prefix": document_hashes,
        "instruction": "Leia os arquivos obrigatórios; hashes não provam compreensão.",
    }
    print(json.dumps(snapshot, ensure_ascii=True, indent=2))

    if head != head_mark.group(1) or tree != tree_mark.group(1):
        print(
            "Checkout mudou desde o estado operacional. Reconcilie o arquivo antes de editar.",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
