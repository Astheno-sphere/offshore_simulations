"""Fuel, energy and emissions from vessel activity (L2 KPI helper). SPEC: build to this docstring.

Bottom-up per agent from the trajectory contract (never from a guessed average):
    fuel_t = sum over rows of P(state, speed) * dt * SFOC / 1e6
- P(state, speed): power by state. sail: propulsion by the propeller (cube) law P = P_ref * (v / v_ref)^3
  + auxiliary; dp: DP power at the hour's Hs/wind (table per vessel class); idle/wait/load/unload: auxiliary.
- Every parameter (P_ref, v_ref, auxiliary kW, DP table, SFOC g/kWh, fuel type) is a sourced scenario value
  (vessel datasheet, paper table) or `assumption: true`; the report lists which.
- CO2 = fuel_t * Cf, with Cf per fuel type from the IMO carbon-factor guideline cited in the scenario
  (e.g. MGO/MDO); CH4/N2O slip for LNG only when the scenario cites factors. Battery-electric states
  (`charge`) report kWh from shore, and grid CO2 only from a cited grid factor.
- Output adds `fuel_t, co2_t, energy_kwh` to SimResult.kpis; absent sources -> keys omitted, never zero.

    def vessel_energy(traj, agents, vessel_params, weather=None) -> pd.DataFrame  # per agent and state
    def kpis(energy_df) -> dict
"""


def vessel_energy(traj, agents, vessel_params, weather=None):
    raise NotImplementedError("spec in offsim/emissions/__init__.py docstring")


def kpis(energy_df):
    raise NotImplementedError("spec in offsim/emissions/__init__.py docstring")
