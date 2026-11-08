import csv
import json
from pathlib import Path

import pytest
import yaml

pytest.importorskip("pdfplumber")
reportlab = pytest.importorskip("reportlab")

from offsim.intake import paper  # noqa: E402


def make_pdf(path: Path) -> Path:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    st = getSampleStyleSheet()
    title = st["Title"]
    title.fontSize = 20
    body = st["BodyText"]
    tbl = Table([["Vessel", "Speed (kn)", "Capacity (t)"], ["PSV-A", "12", "4500"], ["PSV-B", "14", "3200"]])
    tbl.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.black)]))
    story = [
        Paragraph("Supply vessel routing for offshore installations", title),
        Paragraph("Jane Doe, John Smith", body),
        Paragraph("DOI: 10.1016/j.example.2024.01.001 (2024)", body),
        Paragraph("Abstract. We study supply vessel routing with time windows for platforms on the Norwegian "
                  "continental shelf using a heuristic.", body),
        PageBreak(),
        Paragraph("2 Problem description", st["Heading2"]),
        Paragraph("The fleet consists of 3 PSVs sailing at 12 knots. Each installation has a service time of 4 h. "
                  "The average distance is 90 nm. Instances have n = 20 installations.", body),
        Spacer(1, 12), Paragraph("Table 1 lists the vessels.", body), tbl,
        PageBreak(),
        Paragraph("5 Results", st["Heading2"]),
        Paragraph("The best plan reaches a total cost of 1 234 567 NOK with an optimality gap of 0.8%. "
                  "Operations stop when Hs exceeds 2.5 m.", body),
    ]
    SimpleDocTemplate(str(path), pagesize=A4).build(story)
    return path


@pytest.fixture(scope="module")
def pdf(tmp_path_factory):
    d = Path(__file__).parent / "fixtures" / "intake"
    d.mkdir(parents=True, exist_ok=True)
    return make_pdf(d / "synthetic_paper.pdf")


def test_extract_metadata_and_tables(pdf):
    ex = paper.extract(pdf)
    assert ex["source"]["pages"] == 3
    assert ex["metadata"]["doi"].startswith("10.1016/j.example.2024.01.001")
    assert ex["metadata"]["year"] == 2024
    assert "Supply vessel routing" in ex["metadata"]["title"]
    assert any(t["page"] == 2 for p in ex["pages"] for t in p["tables"])
    assert any("Problem description" in h["heading"] for h in ex["headings"])


def test_evidence(pdf):
    ev = paper.evidence(paper.extract(pdf))
    by = lambda k: [e for e in ev if e["kind"] == k]
    sp = [e for e in by("speed") if e["source"] == "text"][0]
    assert sp["page"] == 2 and sp["unit"] == "m/s" and sp["value"] == pytest.approx(6.17, abs=0.01)
    assert sp["orig_value"] == 12 and sp["orig_unit"] == "knots"
    assert any(e["source"] == "table" and e["value"] == pytest.approx(14 * 1852 / 3600, abs=1e-3) for e in by("speed"))
    assert any(e["source"] == "table" and e["value"] == 4500000 and e["unit"] == "kg" for e in by("capacity"))
    assert any(e["value"] == 3 and e["page"] == 2 for e in by("fleet_size"))
    assert any(e["value"] == 14400 and e["unit"] == "s" for e in by("service"))
    assert any(e["value"] == pytest.approx(90 * 1852) for e in by("distance"))
    assert any(e["value"] == 20 for e in by("instance_size"))
    c = by("cost")
    assert any(e["value"] == 1234567 and e["unit"] == "NOK" and e["page"] == 3 for e in c)
    assert any(e["label"] == "total_cost" and e["value"] == 1234567 for e in by("reported_kpi"))
    assert any(e["label"] == "gap_pct" and e["value"] == 0.8 for e in by("reported_kpi"))
    assert any(e["value"] == 2.5 for e in by("weather_limit_hs"))


def test_classify(pdf):
    tags = paper.classify(paper.extract(pdf))
    assert "PSV-PDP" in tags["classes"] and "psv" in tags["mode"] and tags["confidence"] < 1


def test_draft_files_and_nothing_trusted(pdf, tmp_path):
    d = paper.draft(pdf, tmp_path)
    for f in ("extract.json", "evidence.csv", "scenario.draft.yaml", "notes.md"):
        assert (d / f).exists(), f
    assert not (d / "scenario.yaml").exists()
    assert json.loads((d / "extract.json").read_text())["source"]["pages"] == 3
    assert len(list(csv.DictReader((d / "evidence.csv").open()))) > 5
    sc = yaml.safe_load((d / "scenario.draft.yaml").read_text())
    assert sc["draft"] is True and (d / "scenario.draft.yaml").name.endswith(".draft.yaml")
    speed = sc["fleet"][0]["speed_mps"]
    assert speed["value"] is None and speed["src"] is None
    assert any(c["page"] == 2 and abs(c["value"] - 6.17) < 0.01 for c in speed["candidates"])

    def no_values(o):
        if isinstance(o, dict):
            if "candidates" in o:
                assert o["value"] is None and o["src"] is None
            for v in o.values():
                no_values(v)
        elif isinstance(o, list):
            for v in o:
                no_values(v)
    no_values(sc)
    assert "licence" in (d / "notes.md").read_text().lower()


def test_main_cli(pdf, tmp_path, capsys):
    assert paper.main([str(pdf), "--out", str(tmp_path)]) == 0
    assert "draft:" in capsys.readouterr().out


def test_timetable_draft_for_ferry(tmp_path):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    p = tmp_path / "f.pdf"
    c = canvas.Canvas(str(p), pagesize=A4)
    c.setFont("Helvetica-Bold", 18); c.drawString(60, 800, "Ferry timetabling in Molde")
    c.setFont("Helvetica", 11)
    c.drawString(60, 770, "The ferry runs with a headway of 20 min and a dwell time of 2 min.")
    c.save()
    d = paper.draft(p, tmp_path / "out")
    tt = yaml.safe_load((d / "timetable.draft.yaml").read_text())
    assert tt["lines"][0]["mode"] == "ferry" and tt["lines"][0]["headway_min"]["value"] is None
    assert tt["lines"][0]["headway_min"]["candidates"][0]["value"] == 1200
