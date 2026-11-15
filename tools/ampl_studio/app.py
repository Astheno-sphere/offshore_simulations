"""AMPL Studio: local Streamlit GUI for AMPL. Run: python -m streamlit run tools/ampl_studio/app.py

AMPL runs on the laptop only (local install through amplpy). All logic lives in core.py.
"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core  # noqa: E402

st.set_page_config(page_title="AMPL Studio", layout="wide")
st.title("AMPL Studio")

ampl_dir = core.find_ampl_dir()
groups = core.probe_solvers(ampl_dir)
solvers = core.all_solvers(groups)
roots = core.allowed_roots()

with st.sidebar:
    st.subheader("Setup")
    st.write(f"AMPL folder: {ampl_dir if ampl_dir else 'not found (set AMPL_DIR)'}")
    st.write("Allowed roots:")
    for r in roots:
        st.write(f"- {r}")
    st.caption("Ask Claude: the ampl MCP server exposes the same models")

if not ampl_dir or not solvers:
    st.error("No AMPL install or no solver executables found. Set AMPL_DIR to the AMPL folder on this laptop.")
    st.stop()

# --- model source -------------------------------------------------------------------------------------------
st.header("Model")
source = st.radio("Source", ["File from allowed roots", "Paste model text"], horizontal=True)
files = core.list_models(roots)
model_path = data_path = None
model_text = data_text = ""
if source.startswith("File"):
    mods = [p for p in files if p.suffix.lower() in (".mod", ".run")]
    dats = [p for p in files if p.suffix.lower() == ".dat"]
    if not mods:
        st.warning("No .mod or .run files under the allowed roots.")
    else:
        model_path = st.selectbox("Model (.mod or .run)", mods, format_func=lambda p: str(p))
        if model_path.suffix.lower() == ".mod":
            data_path = st.selectbox("Data (.dat, optional)", [None] + dats,
                                     format_func=lambda p: "none" if p is None else str(p))
        try:
            st.code(core.read_checked(model_path, roots), language="text")
        except Exception as e:
            st.error(str(e))
else:
    model_text = st.text_area("Model text", height=220, value=(
        "var x >= 0, <= 3;\nvar y >= 0;\nmaximize z: 3*x + 2*y;\ns.t. a: x + y <= 4;\ns.t. b: x + 3*y <= 6;"))
    data_text = st.text_area("Data text (optional)", height=80)

# --- solver ---------------------------------------------------------------------------------------------------
st.header("Solver")
mode = st.radio("Mode", ["Solve", "Compare solvers"], horizontal=True)
labels = {s: f"{s} ({g})" for g, names in groups.items() for s in names}
if mode == "Solve":
    solver = st.selectbox("Solver", solvers, format_func=lambda s: labels[s])
    chosen = [solver]
else:
    chosen = st.multiselect("Solvers", solvers, default=[s for s in ("highs", "cbc") if s in solvers],
                            format_func=lambda s: labels[s])
options = st.text_input("Solver options", placeholder="outlev=1 timelim=60",
                        help="Becomes: option <solver>_options '...'. Same text for every solver in compare mode.")

if st.button("Solve" if mode == "Solve" else "Compare", type="primary"):
    if not chosen:
        st.warning("Pick at least one solver.")
    elif model_path is None and source.startswith("File"):
        st.warning("No model selected.")
    else:
        kw = dict(options=options, ampl_dir=ampl_dir, roots=roots)
        if model_path is not None:
            kw.update(path=model_path, data_path=data_path)
        else:
            kw.update(model_text=model_text, data_text=data_text)
        with st.spinner("Solving..."):
            st.session_state["results"] = core.compare(chosen, **kw)
            st.session_state["mode"] = mode

results = st.session_state.get("results")
if results:
    st.header("Results")
    if st.session_state.get("mode") == "Compare solvers":
        st.dataframe(core.compare_table(results), hide_index=True, width="stretch")
    for r in results:
        with st.expander(f"{r['solver']}: {r['status'] or 'error'}", expanded=len(results) == 1):
            if r["error"]:
                st.error(r["error"])
            c1, c2, c3 = st.columns(3)
            c1.metric("solve_result", r["status"] or "n/a")
            c2.metric("Time (s)", "n/a" if r["seconds"] is None else f"{r['seconds']:.3f}")
            c3.metric("Objectives", len(r["objectives"]))
            if r["objectives"]:
                st.dataframe(r["objectives"], hide_index=True)
            if r["variables"] is not None and not r["variables"].empty:
                st.subheader("Variables")
                st.dataframe(r["variables"], hide_index=True, width="stretch")
                st.download_button("Download variables CSV", core.variables_csv(r["variables"]),
                                   file_name=f"{Path(r['model']).stem}_{r['solver']}_variables.csv",
                                   mime="text/csv", key=f"csv_{r['solver']}")
            st.subheader("Solver output")
            st.code(r["output"] or "(no output)", language="text")
            if r["log"]:
                st.caption(f"Log: {r['log']}")
