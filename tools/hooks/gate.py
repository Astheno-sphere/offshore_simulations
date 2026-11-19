#!/usr/bin/env python3
"""Harness-level gates for Claude Code (PreToolUse and Stop hooks). Stdlib only. Rules and limits: docs/HOOKS.md.

    python3 -S tools/hooks/gate.py pre    # PreToolUse: JSON on stdin; exit 2 + reason on stderr blocks the call
    python3 -S tools/hooks/gate.py stop   # Stop: prints {"decision":"block","reason":...} to keep the agent working

Hook input fields relied on (confirmed from the working gate in Abhinav Bhardwaj's Junior Architect Pipeline, gate.js, and
not from local docs, which are not installed here): cwd, tool_name, tool_input.{file_path, content, old_string, new_string,
edits[], notebook_path, new_source, command}, stop_hook_active. Exit 2 blocks a PreToolUse call and shows stderr to Claude.

Rules (each is a pure function of the hook input; git and the filesystem are read only through the `Git` object, which a
test replaces):
    H1  nothing but the pipeline writes out/**/report.json, trajectory.csv, agents.csv, run.json, state.json
    H2  writes to rules.py, golden frames, the visual gate and scenario tolerances only on agent/<who>/<id>; a commit that
        changes them carries a `why:` line
    H3  nothing under out/ or data/ goes into git; nothing under out/reference/ ever
    H4  no secret-shaped string (a UUID beside AMPL or licence, a BarentsWatch client secret) in a file, commit or command
    H5  (Stop) no finishing while a changed storyboard names a run whose gates did not pass

Every hook fails OPEN: an internal error is logged to stderr and the call is allowed. Reads and `python -m pytest` are
never blocked. Disable one in an emergency with env OFFSIM_HOOKS_OFF=H2 (comma list, or `all`); see docs/HOOKS.md.
"""
import difflib
import json
import os
import re
import sys

DOC = "docs/HOOKS.md"
RUN_FILES = ("report.json", "trajectory.csv", "agents.csv", "run.json", "state.json")
_NAMES = "|".join(re.escape(n) for n in RUN_FILES)
PROT_REL = re.compile(rf"^out/(?:.+/)?(?:{_NAMES})$")                 # a protected path, root-relative
PROT_ANY = re.compile(rf"(?:^|/)out/(?:[^/]+/)*(?:{_NAMES})$")        # same, when the prefix is a variable or unknown
BARE = re.compile(rf"(?:^|/)(?:{_NAMES})$")                           # after a `cd .../out`: any such name
H2_FILES = ("offsim/cinema/rules.py", "offsim/cinema/visual_gate.py")
H2_PREFIX = ("tests/golden/",)
SCENARIO = re.compile(r"^offsim/papers/[^/]+/scenario[^/]*\.ya?ml$")
TOL = re.compile(r"\b(?:rel_tol|abs_tol|gap_tol|tol|tolerance|tolerances)\b")
BRANCH_OK = re.compile(r"^agent/[^/]+/.+")
UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
UUID_RE = re.compile(UUID)
AMPL_W = re.compile(r"(?i)ampl")
LICENCE_W = re.compile(r"(?i)licen[cs]e")
DATASET_CTX = re.compile(r"(?i)(?:https?:|/|metadata|dataset|record|catalogue|catalog)[\w\s:\"'=./-]{0,12}$")   # a data id, not a key
BW_VALUE = r"""["']?([A-Za-z0-9_\-.~+/!@#%^*]{12,})"""
BW_A = re.compile(rf"(?i)(?:BW_CLIENT_SECRET|BARENTSWATCH\w*SECRET)\s*[:=]\s*{BW_VALUE}")
BW_B = re.compile(rf"(?i)client[_-]?secret\s*[:=]\s*{BW_VALUE}")
BW_CTX = re.compile(r"(?i)barents\s?watch|BW_CLIENT")
PLACEHOLDER = re.compile(r"(?i)^(?:x{3,}|\.{3}|\*{3,}|your|<|changeme|placeholder|example|dummy|secrets\.|os\.|env|none|null|test)")
PY_WRITE = re.compile(r"write_text|write_bytes|to_csv|to_json|json\.dump|\.write\(|open\([^)]*[\"'][wax+]|shutil\.|os\.(?:replace|rename|remove|unlink)|\.touch\(|\.unlink\(")
SEP = re.compile(r"&&|\|\||;|\||\n")
WRAP = re.compile(r"^(?:[({]\s*|(?:\w+=\S*|sudo|env|time|nice|nohup|command|exec|xvfb-run(?:\s+-\S+)*|timeout\s+\S+|uv\s+run|poetry\s+run)\s+)*")
PY = r"(?:\S*/)?python[\d.]*"
PIPE = re.compile(rf"^{PY}\s+(?:-[A-Za-z]+\s+)*-m\s+offsim\s+run\b")
PYTEST = re.compile(rf"^(?:{PY}\s+(?:-[A-Za-z]+\s+)*-m\s+pytest|(?:\S*/)?pytest|(?:\S*/)?py\.test)\b")
WHY = re.compile(r"(?im)^\s*why:\s*\S")
REDIRECT = re.compile(r"(?<![<>&\w-])(?:\d?>>?|&>>?|>\|)\s*([^\s;&|<>]+)")


class Git:
    """Read-only view of the repository. Tests pass an object with the same three methods."""

    def branch(self, root):
        """Current branch name, or None when it cannot be determined (no repo, detached HEAD)."""
        try:
            g = os.path.join(root, ".git")
            if os.path.isfile(g):
                with open(g) as f:
                    line = f.read().strip()
                g = line.split("gitdir:", 1)[1].strip()
                g = g if os.path.isabs(g) else os.path.join(root, g)
            with open(os.path.join(g, "HEAD")) as f:
                head = f.read().strip()
            return head[len("ref: refs/heads/"):] if head.startswith("ref: refs/heads/") else None
        except Exception:
            return None

    def staged(self, root, include_unstaged=False):
        """[(status letter, path)] of the index against HEAD, plus tracked unstaged changes for `commit -a`."""
        import subprocess
        out = []
        for extra in ([["--cached"], []] if include_unstaged else [["--cached"]]):
            r = subprocess.run(["git", "diff", *extra, "--name-status", "--no-renames"], cwd=root, capture_output=True,
                               text=True, timeout=3)
            for ln in r.stdout.splitlines():
                p = ln.split("\t")
                if len(p) >= 2:
                    out.append((p[0][:1], p[-1]))
        return out

    def changed_storyboards(self, root):
        import subprocess
        r = subprocess.run(["git", "status", "--porcelain", "-uall", "--", "*storyboard*.yaml"], cwd=root,
                           capture_output=True, text=True, timeout=3)
        return [ln[3:].strip().strip('"') for ln in r.stdout.splitlines() if len(ln) > 3 and not ln.startswith(" D")]


def disabled(rule, env):
    off = {x.strip().upper() for x in (env.get("OFFSIM_HOOKS_OFF") or "").split(",") if x.strip()}
    return "ALL" in off or rule in off


def block(rule, why, fix=""):
    return rule, f"BLOCKED by offsim hook {rule} ({DOC}#{rule.lower()}): {why}" + (f" {fix}" if fix else "")


def find_root(cwd):
    d = os.path.abspath(cwd)
    while True:
        if os.path.exists(os.path.join(d, ".git")):
            return d
        up = os.path.dirname(d)
        if up == d:
            return os.path.abspath(cwd)
        d = up


def rel_to_root(path, cwd, root):
    """Root-relative posix path, or None when the path lies outside the repository."""
    p = path if os.path.isabs(path) else os.path.join(cwd, path)
    p = os.path.normpath(p)
    r = os.path.relpath(p, root).replace(os.sep, "/")
    return None if r == ".." or r.startswith("../") else r


def strip_tok(t):
    return t.strip().strip("\"'`)}(")


def prot_path(tok, cwd, root, cd_out=False):
    """True when a shell word names a protected run file."""
    t = strip_tok(tok)
    if not t or t.startswith("-"):
        return False
    if cd_out and BARE.search(t):
        return True
    if "$" in t or "`" in t:
        return bool(PROT_ANY.search(t))
    rel = rel_to_root(t, cwd, root)
    return bool(rel and PROT_REL.match(rel))


def writes_of(inp):
    """[(path, new_text, tool)] a file tool would write; path as given."""
    ti = inp.get("tool_input") or {}
    tool = inp.get("tool_name") or ""
    if tool == "Write":
        return [(ti.get("file_path"), ti.get("content") or "", tool)]
    if tool == "Edit":
        return [(ti.get("file_path"), ti.get("new_string") or "", tool)]
    if tool == "MultiEdit":
        return [(ti.get("file_path"), "\n".join(e.get("new_string") or "" for e in ti.get("edits") or []), tool)]
    if tool == "NotebookEdit":
        return [(ti.get("notebook_path"), ti.get("new_source") or "", tool)]
    return []


def new_text_of(path_abs, inp):
    """Full text the file will have after the call, or None when it cannot be worked out."""
    ti = inp.get("tool_input") or {}
    tool = inp.get("tool_name")
    if tool == "Write":
        return ti.get("content") or ""
    try:
        with open(path_abs, encoding="utf-8") as f:
            text = f.read()
    except Exception:
        return None
    edits = [ti] if tool == "Edit" else list(ti.get("edits") or [])
    for e in edits:
        o, n = e.get("old_string"), e.get("new_string") or ""
        if not o or o not in text:
            return None
        text = text.replace(o, n) if e.get("replace_all") else text.replace(o, n, 1)
    return text


def reported_lines(lines):
    """Indexes of lines inside the top-level `reported:` block (the line itself included)."""
    inside, idx = False, set()
    for i, ln in enumerate(lines):
        if re.match(r"^reported\s*:", ln):
            inside = True
            idx.add(i)
        elif inside and ln.strip() and not ln[:1].isspace() and not ln.lstrip().startswith("#"):
            inside = False
        elif inside:
            idx.add(i)
    return idx


def scenario_tolerance_touched(old, new):
    """True when the change from `old` to `new` alters a line of `reported:` or a line naming a tolerance."""
    a, b = old.splitlines(), new.splitlines()
    ra, rb = reported_lines(a), reported_lines(b)
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        if any(i in ra or TOL.search(a[i]) for i in range(i1, i2)) or any(j in rb or TOL.search(b[j]) for j in range(j1, j2)):
            return True
    return False


def h2_path(rel):
    return rel in H2_FILES or rel.startswith(H2_PREFIX)


# ---------------------------------------------------------------------------------------------------------- H4
def secret_shaped(text):
    if not text:
        return False
    for m in UUID_RE.finditer(text):
        before, after = text[max(0, m.start() - 100):m.start()], text[m.end():m.end() + 100]
        if AMPL_W.search(before) or AMPL_W.search(after):
            return True                                # a UUID within 100 characters of AMPL
        if (LICENCE_W.search(before[-40:]) or LICENCE_W.search(after[:40])) and not DATASET_CTX.search(before[-30:]):
            return True                                # beside licence/license, unless it is a dataset id (URL, metadata_uuid)
    if BW_CTX.search(text):
        pats = (BW_A, BW_B)
    else:
        pats = (BW_A,)
    for pat in pats:
        for m in pat.finditer(text):
            v = m.group(1)
            if PLACEHOLDER.match(v) or len(set(v)) < 5:
                continue
            if any(c.isdigit() for c in v) and any(c.isalpha() for c in v):
                return True
    return False


# ---------------------------------------------------------------------------------------------------------- shell
def split_segments(cmd):
    return [s.strip() for s in SEP.split(cmd) if s.strip()]


def unwrap(seg):
    return WRAP.sub("", seg, count=1).strip()


def tokens(seg):
    import shlex
    try:
        return shlex.split(seg)
    except ValueError:
        return seg.split()


def shell_writes_protected(seg, cwd, root, cd_out, depth=0):
    """True when one shell segment writes (or deletes, moves, truncates) a protected run file."""
    for m in REDIRECT.finditer(seg):
        if prot_path(m.group(1), cwd, root, cd_out):
            return True
    s = unwrap(seg)
    if PIPE.match(s) or PYTEST.match(s):
        return False                                   # the pipeline and the tests may write; only a redirect is checked
    toks = tokens(s)
    if not toks:
        return False
    cmd = os.path.basename(toks[0])
    args = [t for t in toks[1:] if not t.startswith(">")]
    nonopt = [t for t in args if not t.startswith("-")]
    P = lambda t: prot_path(t, cwd, root, cd_out)      # noqa: E731
    if cmd in ("tee", "rm", "unlink", "shred", "truncate", "touch", "mv", "rmdir"):
        return any(P(t) for t in nonopt)
    if cmd in ("cp", "install", "ln", "rsync", "scp"):
        dest = None
        for i, t in enumerate(args):
            if t in ("-t", "--target-directory") and i + 1 < len(args):
                dest = args[i + 1]
        srcs = nonopt[:-1] if dest is None else nonopt
        dest = dest or (nonopt[-1] if nonopt else None)
        if dest is None:
            return False
        return P(dest) or any(P(dest.rstrip("/") + "/" + os.path.basename(s)) for s in srcs)
    if cmd in ("sed", "perl", "ruby", "awk", "gawk"):
        inplace = any(t in ("--in-place", "inplace") or (t.startswith("-") and not t.startswith("--") and "i" in t[1:])
                      or t.startswith("-i") for t in args)
        return inplace and any(P(t) for t in nonopt)
    if cmd == "dd":
        return any(t.startswith("of=") and P(t[3:]) for t in args)
    if cmd in ("curl", "wget"):
        for i, t in enumerate(args):
            if t in ("-o", "--output", "-O") and i + 1 < len(args) and P(args[i + 1]):
                return True
            if t.startswith("-o") and len(t) > 2 and P(t[2:]):
                return True
        return False
    if cmd in ("bash", "sh", "zsh", "dash", "eval") and depth < 2:
        inner = [t for t in args if not t.startswith("-")]
        return any(shell_writes_protected(y, cwd, root, cd_out, depth + 1) for x in inner for y in split_segments(x))
    return False


def python_writes_protected(text):
    """A script or -c snippet with a line that names a protected file and calls a write API."""
    for ln in text.splitlines():
        if re.search(_NAMES, ln) and PY_WRITE.search(ln):
            return True
    return False


def h1_bash(cmd, cwd, root):
    cd_out = bool(re.search(r"\bcd\s+[^;&|\n]*\bout\b", cmd))
    if not re.search(_NAMES, cmd):
        return False
    rest = []
    for seg in split_segments(cmd):
        if shell_writes_protected(seg, cwd, root, cd_out):
            return True
        s = unwrap(seg)
        if not (PIPE.match(s) or PYTEST.match(s)):
            rest.append(seg)
    return python_writes_protected("\n".join(rest))


def git_parts(seg):
    """(subcommand, args, cwd_shift) when the segment is a git call, else None."""
    toks = tokens(unwrap(seg))
    if not toks or os.path.basename(toks[0]) != "git":
        return None
    i, shift = 1, None
    while i < len(toks) and toks[i].startswith("-"):
        if toks[i] == "-C" and i + 1 < len(toks):
            shift, i = toks[i + 1], i + 2
        elif toks[i] in ("-c", "--git-dir", "--work-tree", "--namespace") and i + 1 < len(toks):
            i += 2
        else:
            i += 1
    return (toks[i], toks[i + 1:], shift) if i < len(toks) else None


def h3_path(rel):
    return rel in ("out", "data") or rel.startswith(("out/", "data/")) or bool(re.search(r"(?:^|/)out/reference(?:/|$)", rel))


def h3_add(args, cwd, root):
    force = any(a in ("-f", "--force") or (a.startswith("-") and not a.startswith("--") and "f" in a[1:]) for a in args)
    paths = [a for a in args if not a.startswith("-")]
    for a in paths:
        if a in (".", "*", ":/", ":(top)") or a.endswith("/."):
            if force:
                return True                            # a forced add of the whole tree takes the ignored out/ and data/
            continue
        rel = rel_to_root(a, cwd, root)
        if rel and h3_path(rel):
            return True
    return force and any(a in ("-A", "--all") for a in args)


def commit_text(seg, cmd, cwd):
    """The commit message as far as it can be seen: the whole command (covers -m and heredocs) plus a -F file."""
    text = cmd
    toks = tokens(unwrap(seg))
    for i, t in enumerate(toks):
        f = toks[i + 1] if t in ("-F", "--file") and i + 1 < len(toks) else (t[7:] if t.startswith("--file=") else None)
        if f and f != "-":
            try:
                with open(f if os.path.isabs(f) else os.path.join(cwd, f), encoding="utf-8") as fh:
                    text += "\n" + fh.read()
            except Exception:
                pass
    return text


# ---------------------------------------------------------------------------------------------------------- PreToolUse
def decide_pre(inp, env=None, git=None):
    """None to allow, else (rule, message). Pure apart from the reads the `git` object and the target file allow."""
    env = os.environ if env is None else env
    git = git or Git()
    tool = inp.get("tool_name") or ""
    ti = inp.get("tool_input") or {}
    cwd = inp.get("cwd") or os.getcwd()
    root = find_root(cwd)
    cmd = ti.get("command") or "" if tool == "Bash" else ""
    segs = split_segments(cmd) if cmd else []
    only_pytest = bool(segs) and all(PYTEST.match(unwrap(s)) for s in segs)
    if only_pytest:
        return None                                    # `python -m pytest` is never blocked

    # H4 first: the secret may sit in anything the tool is about to write or run.
    if not disabled("H4", env):
        texts = [cmd] if cmd else [t for _, t, _ in writes_of(inp)]
        if any(secret_shaped(t) for t in texts):
            return block("H4", "a secret-shaped string is present.",
                         "Keep licences and client secrets in GitHub secrets or your own terminal, never in a file, commit or command.")

    for path, new, wtool in writes_of(inp):
        if not path:
            continue
        rel = rel_to_root(path, cwd, root)
        if rel is None:
            continue
        if not disabled("H1", env) and PROT_REL.match(rel):
            return block("H1", f"{rel} is written only by `python -m offsim run`.",
                         "Run the pipeline; never hand-write a report, trajectory or run state.")
        if not disabled("H2", env):
            hit = h2_path(rel)
            if not hit and SCENARIO.match(rel):
                abs_p = os.path.join(root, rel)
                old = ""
                try:
                    with open(abs_p, encoding="utf-8") as f:
                        old = f.read()
                except Exception:
                    pass
                nt = new_text_of(abs_p, inp)
                hit = scenario_tolerance_touched(old, nt) if nt is not None else bool(TOL.search(new) or TOL.search(ti.get("old_string") or ""))
            if hit:
                b = git.branch(root)
                if b is not None and not BRANCH_OK.match(b):
                    return block("H2", f"{rel} sets what a gate or a golden accepts and may change only on a branch agent/<who>/<id> (now on {b}).",
                                 "Branch first; the commit message then needs a `why:` line.")

    if tool == "Bash" and cmd:
        if not disabled("H1", env) and h1_bash(cmd, cwd, root):
            return block("H1", "a shell command writes out/**/report.json, trajectory.csv or run state.",
                         "Only `python -m offsim run` writes these; reading them is fine.")
        for seg in segs:
            g = git_parts(seg)
            if not g:
                continue
            sub, args, shift = g
            gcwd = os.path.join(cwd, shift) if shift else cwd
            if sub == "add" and not disabled("H3", env) and h3_add(args, gcwd, root):
                return block("H3", "git add of out/ or data/ (or a forced add of the whole tree). Nothing under out/reference/ ever.",
                             "Run outputs and data are published as releases or artifacts, never committed.")
            if sub == "commit":
                try:
                    allflag = any(a == "--all" or (a.startswith("-") and not a.startswith("--") and "a" in a[1:]) for a in args)
                    staged = git.staged(root, include_unstaged=allflag)
                except Exception as e:
                    sys.stderr.write(f"offsim hook: could not read the index ({e}); commit checks skipped\n")
                    staged = []
                if not disabled("H3", env) and any(h3_path(p) for s, p in staged if s != "D"):
                    return block("H3", "the index holds files under out/ or data/ (or out/reference/).",
                                 "Unstage them: git restore --staged <path>.")
                if not disabled("H2", env):
                    h2s = [p for s, p in staged if s != "A" and (h2_path(p) or SCENARIO.match(p))]
                    if h2s and not WHY.search(commit_text(seg, cmd, gcwd)):
                        return block("H2", f"this commit changes {h2s[0]}{' and more' if len(h2s) > 1 else ''} without a `why:` line.",
                                     "Add a line `why: <reason>` to the commit message.")
    return None


# ---------------------------------------------------------------------------------------------------------- Stop
def decide_stop(inp, env=None, git=None):
    """None to let the agent finish, else the reason to keep it working (H5)."""
    env = os.environ if env is None else env
    if disabled("H5", env) or inp.get("stop_hook_active"):
        return None                                    # stop_hook_active stops the hook from looping (pattern from gate.js)
    git = git or Git()
    root = find_root(inp.get("cwd") or os.getcwd())
    bad = []
    for sb in git.changed_storyboards(root)[:8]:
        try:
            with open(os.path.join(root, sb), encoding="utf-8") as f:
                m = re.search(r"(?m)^run:\s*[\"']?([^\s\"'#]+)", f.read())
            if not m:
                continue
            with open(os.path.join(root, m.group(1), "report.json"), encoding="utf-8") as f:
                rep = json.load(f)
        except Exception:
            continue                                   # no run on disk (out/ is not synced): cannot judge, allow
        failed = [g for g, r in (rep.get("gates") or {}).items() if g != "4_paper" and not (r or {}).get("pass")]
        if failed:
            bad.append(f"{sb} -> {m.group(1)}/report.json (gates not passed: {', '.join(failed)})")
    if not bad:
        return None
    return (f"BLOCKED by offsim hook H5 ({DOC}#h5): a storyboard in the working tree names a run that failed its gates: "
            + "; ".join(bad) + ". Fix the run (python -m offsim doctor <report.json>) or remove the storyboard; never render or narrate a failed run.")


def main(argv):
    mode = argv[1] if len(argv) > 1 else "pre"
    try:
        raw = sys.stdin.read()
        inp = json.loads(raw) if raw.strip() else {}
        if not isinstance(inp, dict):
            return 0
        if mode == "stop":
            reason = decide_stop(inp)
            if reason:
                sys.stdout.write(json.dumps({"decision": "block", "reason": reason}))
            return 0
        res = decide_pre(inp)
        if res:
            sys.stderr.write(res[1] + "\n")
            return 2
    except Exception as e:                             # fail open: a broken gate must not brick a session
        sys.stderr.write(f"offsim hook: internal error, call allowed ({type(e).__name__}: {e})\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
