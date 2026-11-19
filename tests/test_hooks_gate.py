"""tools/hooks/gate.py: every hook has a seeded violation that is blocked with the right message and a legitimate twin
that is allowed. Secret-shaped strings are built at run time so this file never contains one (hook H4 would stop it)."""
import importlib.util
import json
import subprocess
import sys
import time

import pytest

from conftest import ROOT

GATE = ROOT / "tools/hooks/gate.py"
spec = importlib.util.spec_from_file_location("offsim_hook_gate", GATE)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

FAKE_UUID = "-".join(["1a2b3c4d", "5e6f", "4a1b", "8c9d", "0e1f2a3b4c5d"])
FAKE_BW = "Zq" + "8Xk2" + "Lm9Pw4Rt7"


class FakeGit:
    def __init__(self, branch="agent/claude/J2-hooks", staged=(), storyboards=()):
        self._b, self._s, self._sb = branch, list(staged), list(storyboards)

    def branch(self, root):
        return self._b

    def staged(self, root, include_unstaged=False):
        return self._s

    def changed_storyboards(self, root):
        return self._sb


@pytest.fixture
def repo(tmp_path):
    (tmp_path / ".git").mkdir()
    return tmp_path


def bash(repo, cmd, **kw):
    return gate.decide_pre({"tool_name": "Bash", "cwd": str(repo), "tool_input": {"command": cmd}}, env={}, git=kw.get("git") or FakeGit())


def file_tool(repo, tool, path, env=None, git=None, **ti):
    return gate.decide_pre({"tool_name": tool, "cwd": str(repo), "tool_input": {"file_path": path, **ti}}, env=env or {}, git=git or FakeGit())


def rule(res):
    return res[0] if res else None


# --- H1 ------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("cmd", [
    "python -m offsim run offsim/papers/x/scenario.yaml",
    "python -m offsim run x.yaml --out out/a --seconds 5",
    "PYTHONPATH=. python3 -m offsim run x.yaml && cat out/a/report.json",
    "cat out/a/report.json",
    "jq .status out/a/report.json",
    "cp out/a/report.json /tmp/copy.json",
    "grep -c pass out/a/report.json > /tmp/n.txt",
    "python -m pytest -q tests",
    "python -c \"import json;print(json.load(open('out/a/report.json'))['status'])\"",
    "ls out/a",
    "echo {} > out/a/notes.md",
])
def test_h1_allows_the_pipeline_reads_and_tests(repo, cmd):
    assert bash(repo, cmd) is None


@pytest.mark.parametrize("cmd", [
    "echo {} > out/a/report.json",
    "echo '{}'>out/a/report.json",
    "echo x >> out/a/trajectory.csv",
    "echo {} | tee out/a/report.json",
    "cp /tmp/r.json out/a/report.json",
    "cp /tmp/report.json out/a/",
    "mv /tmp/r.json out/a/report.json",
    "sed -i 's/false/true/' out/a/report.json",
    "rm out/a/report.json",
    "truncate -s 0 out/a/trajectory.csv",
    "python -c \"open('out/a/report.json','w').write('{}')\"",
    "python - <<'EOF'\nimport pathlib\npathlib.Path('out/a/report.json').write_text('{}')\nEOF",
    "bash -c \"echo {} > out/a/report.json\"",
    "cd out/a && echo {} > report.json",
    "python -m offsim run x.yaml > out/a/report.json",
    "python -m pytest -q tests; echo {} > out/a/report.json",
    "echo {} > out/a/state.json",
])
def test_h1_blocks_hand_written_run_files(repo, cmd):
    res = bash(repo, cmd)
    assert rule(res) == "H1", cmd
    assert "docs/HOOKS.md" in res[1] and "offsim hook H1" in res[1]


def test_h1_file_tools(repo):
    for tool, extra in (("Write", {"content": "{}"}), ("Edit", {"old_string": "a", "new_string": "b"}),
                        ("MultiEdit", {"edits": [{"old_string": "a", "new_string": "b"}]})):
        assert rule(file_tool(repo, tool, "out/a/report.json", **extra)) == "H1"
        assert rule(file_tool(repo, tool, str(repo / "out/deep/er/trajectory.csv"), **extra)) == "H1"
    assert file_tool(repo, "Write", "out/a/notes.md", content="x") is None
    assert file_tool(repo, "Write", "docs/report.json", content="x") is None
    assert file_tool(repo, "Read", "out/a/report.json") is None


def test_h1_can_be_disabled_by_env(repo):
    assert file_tool(repo, "Write", "out/a/report.json", env={"OFFSIM_HOOKS_OFF": "H1"}, content="{}") is None
    assert rule(file_tool(repo, "Write", "out/a/report.json", env={"OFFSIM_HOOKS_OFF": "H2"}, content="{}")) == "H1"


# --- H2 ------------------------------------------------------------------------------------------------------
def test_h2_golden_and_rules_need_an_agent_branch(repo):
    main = FakeGit(branch="main")
    for p in ("offsim/cinema/rules.py", "tests/golden/findings.png", "offsim/cinema/visual_gate.py"):
        res = file_tool(repo, "Edit", p, git=main, old_string="a", new_string="b")
        assert rule(res) == "H2" and "agent/<who>/<id>" in res[1] and "why:" in res[1], p
        assert file_tool(repo, "Edit", p, git=FakeGit(branch="agent/claude/J2-hooks"), old_string="a", new_string="b") is None
    assert file_tool(repo, "Edit", "offsim/cinema/camera.py", git=main, old_string="a", new_string="b") is None
    assert file_tool(repo, "Edit", "offsim/cinema/rules.py", git=FakeGit(branch=None), old_string="a", new_string="b") is None  # unknown: open


SCEN = "name: x\nsim:\n  seed: 1\nreported:\n  plan_cost:\n    value: 9980\n    rel_tol: 0.05\nstory:\n  question: q\n"


def test_h2_scenario_tolerance_and_reported_values(repo):
    p = repo / "offsim/papers/p/scenario.yaml"
    p.parent.mkdir(parents=True)
    p.write_text(SCEN)
    main = FakeGit(branch="main")
    assert rule(file_tool(repo, "Edit", str(p), git=main, old_string="rel_tol: 0.05", new_string="rel_tol: 0.5")) == "H2"
    assert rule(file_tool(repo, "Edit", str(p), git=main, old_string="value: 9980", new_string="value: 9000")) == "H2"
    assert rule(file_tool(repo, "Write", str(p), git=main, content=SCEN.replace("0.05", "0.5"))) == "H2"
    assert file_tool(repo, "Edit", str(p), git=main, old_string="question: q", new_string="question: why") is None
    assert file_tool(repo, "Write", str(p), git=main, content=SCEN.replace("seed: 1", "seed: 2")) is None
    assert file_tool(repo, "Edit", str(p), git=FakeGit(), old_string="rel_tol: 0.05", new_string="rel_tol: 0.5") is None


def test_h2_commit_needs_a_why_line(repo):
    g = FakeGit(staged=[("M", "offsim/cinema/rules.py")])
    res = bash(repo, "git commit -m 'raise zoom cap'", git=g)
    assert rule(res) == "H2" and "why:" in res[1]
    assert bash(repo, "git commit -m 'raise zoom cap\n\nwhy: the paper shot needs 0.4'", git=g) is None
    assert bash(repo, "git commit -m \"$(cat <<'EOF'\nraise zoom cap\n\nwhy: measured\nEOF\n)\"", git=g) is None
    msg = repo / "msg.txt"
    msg.write_text("raise\n\nwhy: measured\n")
    assert bash(repo, "git commit -F msg.txt", git=g) is None
    # a new golden or an unrelated file needs no why
    assert bash(repo, "git commit -m x", git=FakeGit(staged=[("A", "tests/golden/new.png"), ("M", "offsim/a.py")])) is None


# --- H3 ------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("cmd", ["git add out/x.png", "git add data/world/a.json", "git add -f out/reference/clip.mp4",
                                 "git add -f .", "git -C . add out/x.png", "git add -A out", "cd /tmp && git add out"])
def test_h3_blocks_adding_out_and_data(repo, cmd):
    res = bash(repo, cmd.replace("cd /tmp && ", ""))
    assert rule(res) == "H3" and "docs/HOOKS.md" in res[1], cmd


@pytest.mark.parametrize("cmd", ["git add offsim/pipeline.py", "git add -A", "git add .", "git add tests/test_hooks_gate.py docs/HOOKS.md",
                                 "git status", "git diff --stat out/"])
def test_h3_allows_ordinary_git(repo, cmd):
    assert bash(repo, cmd) is None


def test_h3_blocks_a_commit_whose_index_holds_out_or_data(repo):
    assert rule(bash(repo, "git commit -m x", git=FakeGit(staged=[("A", "out/reference/a.mp4")]))) == "H3"
    assert rule(bash(repo, "git commit -m x", git=FakeGit(staged=[("A", "data/w.json")]))) == "H3"
    assert bash(repo, "git commit -m x", git=FakeGit(staged=[("M", "offsim/a.py")])) is None


# --- H4 ------------------------------------------------------------------------------------------------------
def test_h4_commit_message_with_uuid_beside_ampl_is_blocked_without_echo(repo, capsys):
    cmd = f"git commit -m 'fix solve\n\nAMPL licence {FAKE_UUID}'"
    res = bash(repo, cmd)
    assert rule(res) == "H4"
    assert "a secret-shaped string is present" in res[1]
    assert FAKE_UUID not in res[1] and FAKE_UUID[:8] not in res[1]
    # same through the real entry point: exit 2, nothing echoed on either stream
    r = subprocess.run([sys.executable, str(GATE), "pre"], capture_output=True, text=True, cwd=repo,
                       input=json.dumps({"tool_name": "Bash", "cwd": str(repo), "tool_input": {"command": cmd}}))
    assert r.returncode == 2 and FAKE_UUID not in r.stderr + r.stdout and "a secret-shaped string is present" in r.stderr


def test_h4_files_and_the_legitimate_twins(repo):
    assert rule(file_tool(repo, "Write", "notes.md", content=f"licence: {FAKE_UUID}\n")) == "H4"
    assert rule(file_tool(repo, "Edit", "a.yml", old_string="x", new_string=f"{FAKE_UUID} is the AMPL key")) == "H4"
    assert rule(file_tool(repo, "Write", "a.env", content=f"BW_CLIENT_SECRET={FAKE_BW}\n")) == "H4"
    assert rule(file_tool(repo, "Write", "a.py", content=f"# barentswatch\nclient_secret = '{FAKE_BW}'\n")) == "H4"
    ok = ["AMPL licence goes in the secret AMPL_LICENSE_UUID, never in a file",
          "secrets.AMPL_LICENSE_UUID",
          f"session {FAKE_UUID} was a random run id" + " filler" * 40 + " the AMPL solver",
          'self.client_secret = client_secret or os.environ.get("BW_CLIENT_SECRET", "")',
          f'url: "https://data.norge.no/en/datasets/{FAKE_UUID}", layer: world, licence: open',
          f"metadata_uuid: {FAKE_UUID}\n    projection_code: 25832\n    name: DTM\n    licence: open",
          "BW_CLIENT_SECRET=$BW_CLIENT_SECRET",
          "BW_CLIENT_SECRET=<your secret>",
          "export BW_CLIENT_SECRET=xxxxxxxxxxxx"]
    for t in ok:
        assert file_tool(repo, "Write", "n.md", content=t) is None, t
    assert bash(repo, f"python -m pytest -q tests -k 'ampl {FAKE_UUID}'") is None      # pytest is never blocked


# --- H5 ------------------------------------------------------------------------------------------------------
def storyboard(repo, passed):
    d = repo / "out/x"
    d.mkdir(parents=True, exist_ok=True)
    (d / "report.json").write_text(json.dumps({"gates": {"0_provenance": {"pass": True}, "2_physics": {"pass": passed},
                                                         "4_paper": {"pass": False}}}))
    (repo / "offsim/papers/x").mkdir(parents=True, exist_ok=True)
    (repo / "offsim/papers/x/storyboard.yaml").write_text("id: x\nrun: out/x\nshots: []\n")
    return FakeGit(storyboards=["offsim/papers/x/storyboard.yaml"])


def test_h5_stop_refuses_a_storyboard_on_a_failed_run(repo):
    g = storyboard(repo, passed=False)
    reason = gate.decide_stop({"cwd": str(repo)}, env={}, git=g)
    assert reason and "H5" in reason and "2_physics" in reason and "docs/HOOKS.md" in reason
    assert gate.decide_stop({"cwd": str(repo), "stop_hook_active": True}, env={}, git=g) is None   # no loop
    assert gate.decide_stop({"cwd": str(repo)}, env={"OFFSIM_HOOKS_OFF": "H5"}, git=g) is None


def test_h5_stop_allows_passed_missing_and_unchanged(repo):
    assert gate.decide_stop({"cwd": str(repo)}, env={}, git=storyboard(repo, passed=True)) is None   # 4_paper does not count
    (repo / "out/x/report.json").unlink()
    assert gate.decide_stop({"cwd": str(repo)}, env={}, git=FakeGit(storyboards=["offsim/papers/x/storyboard.yaml"])) is None
    assert gate.decide_stop({"cwd": str(repo)}, env={}, git=FakeGit()) is None


def test_h5_entry_point_prints_a_block_decision(repo, monkeypatch):
    storyboard(repo, passed=False)
    monkeypatch.setattr(gate, "Git", lambda: FakeGit(storyboards=["offsim/papers/x/storyboard.yaml"]))
    out = []
    monkeypatch.setattr(sys, "stdin", type("S", (), {"read": lambda self: json.dumps({"cwd": str(repo)})})())
    monkeypatch.setattr(sys.stdout, "write", out.append)
    assert gate.main(["gate.py", "stop"]) == 0
    assert json.loads("".join(out))["decision"] == "block"


# --- fail open, speed, wiring --------------------------------------------------------------------------------
@pytest.mark.parametrize("raw", ["", "not json", "[1,2]", "null", '{"tool_name": "Bash", "tool_input": "oops"}',
                                 '{"tool_name": "Write", "tool_input": {"file_path": 5}}'])
def test_malformed_input_is_allowed(raw):
    for mode in ("pre", "stop"):
        r = subprocess.run([sys.executable, str(GATE), mode], input=raw, capture_output=True, text=True, timeout=10)
        assert r.returncode == 0 and "decision" not in r.stdout, (mode, raw, r.stderr)


def test_internal_error_fails_open(monkeypatch, capsys):
    monkeypatch.setattr(gate, "decide_pre", lambda *a, **k: 1 / 0)
    monkeypatch.setattr(sys, "stdin", type("S", (), {"read": lambda self: json.dumps({"tool_name": "Bash", "tool_input": {"command": "x"}})})())
    assert gate.main(["gate.py", "pre"]) == 0
    assert "internal error, call allowed" in capsys.readouterr().err


def test_a_decision_takes_well_under_100_ms(repo):
    cmds = ["python -m offsim run x.yaml", "echo {} > out/a/report.json", "git add out/x.png", "cat out/a/report.json",
            "git commit -m 'x'", "ls"] * 20
    t = time.perf_counter()
    for c in cmds:
        bash(repo, c)
    assert (time.perf_counter() - t) / len(cmds) < 0.1


def test_settings_wire_the_hooks_to_an_existing_script():
    s = json.loads((ROOT / ".claude/settings.json").read_text())
    pre = s["hooks"]["PreToolUse"][0]
    assert {"Write", "Edit", "MultiEdit", "Bash"} <= set(pre["matcher"].split("|"))
    assert all("tools/hooks/gate.py" in h["command"] for h in pre["hooks"] + s["hooks"]["Stop"][0]["hooks"])
    assert GATE.exists() and (ROOT / "docs/HOOKS.md").exists()
