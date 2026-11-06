"""`python -m offsim resume`: where are we, what is unfinished, what is next. Read-only; safe to run any time,
by any session (human or Claude), after any interruption (rate limit, crash, new day).

Sources of truth it reads: git (branch, unpushed commits, dirty files, worktrees on build/* branches), docs/ROADMAP.md
(rows without ✔ are open), docs/AUDIT.md (open risks), catalog (pulled vs listed), tests (optional quick run),
and docs/RESUME.md (the hand-written log of the last session: decisions, half-done work, exact next command).
"""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sh(*cmd):
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    return r.stdout.strip()


def open_roadmap():
    rows = []
    for line in (ROOT / "docs/ROADMAP.md").read_text().splitlines():
        if line.startswith("| ") and not line.startswith("| #") and not line.startswith("|---") and "✔" not in line.split("|")[2]:
            cells = [c.strip() for c in line.strip("|").split("|")]
            rows.append(f"{cells[0]:>3}  {cells[1][:110]}  [{cells[2]}]")
    return rows


def open_risks():
    text = (ROOT / "docs/AUDIT.md").read_text()
    m = re.search(r"## Open risks.*?\n(.*?)(\n## |\Z)", text, re.S)
    out = [l.strip("- ").strip() for l in (m.group(1).splitlines() if m else []) if l.startswith("- ")]
    m3 = re.search(r"Open from audit \d+: (.*?)\n\n", text, re.S)
    if m3:
        out.append(m3.group(1).replace("\n", " "))
    return out


def worktrees():
    out, cur = [], {}
    for line in sh("git", "worktree", "list", "--porcelain").splitlines() + [""]:
        if not line:
            if cur.get("branch", "").startswith("refs/heads/build/"):
                path = cur["worktree"]
                b = cur["branch"].split("/", 2)[2]
                dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=path, capture_output=True, text=True).stdout
                ahead = sh("git", "log", "--oneline", f"main..{b}")
                merged = not ahead
                out.append(f"{b:16s} {path}  {'MERGED' if merged else str(len(ahead.splitlines())) + ' commit(s) not in main'}"
                           f"{'  + UNCOMMITTED changes' if dirty.strip() else ''}")
            cur = {}
            continue
        k, _, v = line.partition(" ")
        cur[k] = v
    return out


def catalog_counts():
    import yaml
    cat = yaml.safe_load((ROOT / "catalog/tools.yaml").read_text())["tools"]
    pulled = sum(t["status"] in ("tested", "wired", "installed") for t in cat)
    return f"{pulled} pulled / {len(cat)} listed"


def main(run_tests=False):
    print("== offshore_simulations · resume ==")
    print(f"branch {sh('git', 'branch', '--show-current')} @ {sh('git', 'log', '-1', '--format=%h %s')}")
    sh("git", "fetch", "-q", "origin", "main")
    unpushed = sh("git", "log", "--oneline", "origin/main..HEAD")
    print("unpushed:", f"{len(unpushed.splitlines())} commit(s) — git push origin main" if unpushed else "none")
    dirty = sh("git", "status", "--porcelain")
    print("uncommitted:", (str(len(dirty.splitlines())) + " file(s)") if dirty else "none")
    wt = worktrees()
    print("\n-- build worktrees (parallel work; merge or finish these first)")
    print("\n".join(wt) if wt else "none")
    print("\n-- open roadmap steps")
    print("\n".join(open_roadmap()) or "none")
    print("\n-- open risks (docs/AUDIT.md)")
    for r in open_risks():
        print(" -", r[:160])
    print("\n-- catalog:", catalog_counts())
    log = ROOT / "docs/RESUME.md"
    if log.exists():
        m = re.search(r"## Next\n(.*?)(\n## |\Z)", log.read_text(), re.S)
        if m:
            print("\n-- next (docs/RESUME.md)\n" + m.group(1).strip())
    if run_tests:
        print("\n-- tests:", subprocess.run(["python", "-m", "pytest", "-q", "tests"], cwd=ROOT, capture_output=True,
                                            text=True).stdout.strip().splitlines()[-1])
    return 0
