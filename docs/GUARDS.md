# Guards: which test or gate enforces each hard rule

Every bullet under "Hard rules" in `AGENTS.md` has a row here. `tests/test_concordance.py` fails when a rule has no row,
when a guard named here does not exist, or when a row describes a rule that `AGENTS.md` no longer states.

Guard forms: `tests/x.py::test_name` (pytest id), `gate:<id>` (a gate in `offsim/pipeline.py`), `ci:<path>` and `path:<path>`
(a file that must exist). The rule column repeats the start of the bullet in `AGENTS.md`; edit both together.

| Rule | Guard |
|---|---|
| Never render, narrate or post a result that failed a gate | `tests/test_pipeline_motion.py::test_storyboard_refuses_literals_and_failed_runs`, `tests/test_montecarlo.py::test_run_experiment_blocks_on_contract_failure_and_needs_builder`, `tests/test_pipeline_registry.py::test_failed_ensemble_stops_at_3e` |
| Every scenario value has a source (page/table) or `assumption: true` | `tests/test_pipeline_motion.py::test_unsourced_values_and_unsupported_classes_stop_at_gate_0`, `tests/test_cad_marine_air.py::test_every_dim_is_sourced`, `gate:0_provenance` |
| On-screen sentences are chosen from measured values | `tests/test_story_shots.py::test_narrate_refuses_unsafe_expressions`, `tests/test_story_shots.py::test_narrate_missing_names_are_errors_never_defaults`, `tests/test_physics.py::test_narration_follows_measurement` |
| New solver/engine = implement `offsim/engines/base.py` | `tests/test_engines_core.py::test_registry_lists_every_tool_we_ship`, `tests/test_wind_engines.py::test_wombat_refuses_instead_of_approximating`, `tests/test_road.py::test_engine_unsupported_instead_of_approximating`, `tests/test_concordance.py::test_engines_doc_lists_exactly_the_registered_solvers_and_engines`, `tests/test_repo.py::test_catalog_is_valid_and_docs_are_current` |
| Visual work follows `docs/STYLE_REFERENCE.md` | `tests/test_repo.py::test_rules_and_sourced_weather_bands`, `tests/test_camera.py::test_shot_plan_flags_too_fast_zoom_and_passes_demo`, `tests/test_cad_drawing.py::test_story_check_gates_asset_shots`, `tests/test_cad_drawing.py::test_qa_passes_on_matching_dims_and_fails_on_5pct_wrong`, `tests/test_visual_gate.py::test_golden_frames_pass_the_gate_strict`, `tests/test_visual_gate.py::test_check_refuses_a_shot_that_fails_and_names_the_rule` |
| Run `python -m pytest -q tests` before every commit | `ci:.github/workflows/tests.yml` |

## Other rules and their guards (CLAUDE.md, SYSTEM_PLAN section 7)

Not in AGENTS.md, but enforced the same way.

| Rule | Guard |
|---|---|
| Layers import only downward; engines never fetch | `tests/test_architecture.py::test_layer_map_points_at_real_code` |
| Catalog `tested`/`wired`/`installed` needs evidence paths | `tests/test_repo.py::test_catalog_is_valid_and_docs_are_current` |
| No package in requirements without an import or a catalog reason | `tests/test_concordance.py::test_every_pinned_package_is_imported_or_explained_in_the_catalog` |
| Spec stubs are on the roadmap | `tests/test_concordance.py::test_every_spec_stub_module_is_named_in_the_roadmap` |
| Docs and skills name only real commands, paths, workflow inputs | `tests/test_concordance.py::test_cli_commands_named_in_docs_and_skills_exist`, `tests/test_concordance.py::test_paths_cited_in_agent_docs_and_skills_exist`, `tests/test_concordance.py::test_workflow_inputs_named_in_docs_exist_in_the_workflow_yaml` |
| The gate list in the docs is the gate list in the code | `tests/test_concordance.py::test_gate_list_in_code_and_docs_agree` |
| Every section and findings frame passes the visual gate before a storyboard is accepted (`offsim/cinema/visual_gate.py`, rules edges / strokes / palette / accent / contrast / type_scale / margins / balance) | `tests/test_visual_gate.py::test_check_refuses_a_shot_that_fails_and_names_the_rule`, `tests/test_visual_gate.py::test_check_accepts_a_storyboard_that_passes_the_gate`, `tests/test_visual_gate.py::test_shot_visual_block_strict_and_spec_overrides` |
| Each gate rule catches the failure it names (empty, mush, off-palette, accent flood, low contrast, clipped ink, empty half, thin strokes) | `tests/test_visual_gate.py::test_empty_frame_is_caught_as_empty`, `tests/test_visual_gate.py::test_mush_is_caught_as_too_many_edges`, `tests/test_visual_gate.py::test_off_palette_is_caught_not_the_edges`, `tests/test_visual_gate.py::test_accent_flood_is_caught`, `tests/test_visual_gate.py::test_low_contrast_text_is_caught_from_text_metadata`, `tests/test_visual_gate.py::test_clipped_ink_is_caught_at_the_edge`, `tests/test_visual_gate.py::test_empty_half_is_caught_balanced_frame_is_not`, `tests/test_visual_gate.py::test_thin_strokes_are_caught_at_the_delivered_size` |
| Every gate threshold carries its source (a STYLE_REFERENCE rule or a golden-frame measurement) | `tests/test_visual_gate.py::test_gate_spec_is_sourced_data_and_unknown_keys_refuse` |
| Golden frames are regenerated from the renderers, not edited; drift is caught structurally (per-region ink and edge density), not by pixels | `tests/test_visual_gate.py::test_goldens_match_what_the_renderers_produce_today`, `tests/test_visual_gate.py::test_compare_ignores_pixel_noise_and_flags_structural_change`, `path:tests/golden/make_goldens.py` |
| Finding frames are drawn with skia and Inter on a three-size type scale (rule 17) | `tests/test_visual_gate.py::test_findings_port_is_skia_with_the_three_size_scale`, `tests/test_visual_gate.py::test_findings_renderers_pass_the_gate_at_the_delivered_size` |
