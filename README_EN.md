# Lucifer_Engine

> **한국어:** [README.md](README.md)

Lucifer's fall was not a free fall.
It was an orbit. A calculated curve. A trajectory drawn knowing it would never return.

This engine computes that orbit.

`Lucifer_Engine` is the branding name. The actual package is `lucifer_engine`.

---

## What It Is

`Lucifer_Engine` is the **orbital propagation, maneuver planning, and health assessment engine** that takes over from `Rocket_Spirit` at MECO (Main Engine Cut-Off) and orbital insertion (NOMINAL phase).

```
Rocket_Spirit NOMINAL exit (h=444km, v≈7.6km/s)
        ↓  StateVector handoff
Lucifer_Engine
  ├── Kepler element calculation (a, e, i, Ω, ω, ν)
  ├── Orbit health assessment (Ω — 5 components)
  ├── Maneuver planning (circularize, Hohmann, plane change, deorbit)
  ├── Orbit propagation (Kepler + J2 perturbation)
  └── NOMINAL orbit determination
```

---

## Rocket_Spirit Integration (v0.1.0)

```python
from lucifer_engine import OrbitAgent, MissionProfile
from lucifer_engine import state_vector_from_rocket_spirit

# Receive Rocket_Spirit NOMINAL state
sv = state_vector_from_rocket_spirit(rocket_state)

# Initialize orbit agent
mission = MissionProfile(target_altitude_m=444_000.0)
agent = OrbitAgent(mission)

# Inject → plan maneuvers → reach NOMINAL
health = agent.inject(sv)
plan   = agent.plan_maneuvers()
success, results = agent.run_to_nominal(max_steps=200, dt_s=60.0)

print(agent.summary())
```

---

## Layer Structure

```
lucifer_engine/
├── contracts/schemas.py     — StateVector, KeplerElements, OrbitPhase,
│                              OrbitHealthReport, MissionProfile, ManeuverPlan
├── mechanics/
│   ├── kepler.py            — State vector ↔ Kepler elements, propagation, Vis-Viva
│   ├── maneuvers.py         — Circularization, Hohmann, plane change, deorbit
│   └── propagator.py        — Kepler propagation, J2 perturbation, single step
├── health/orbit_health.py   — Ω 5-component health assessment
├── bridges/
│   └── rocket_spirit_bridge.py — Rocket_Spirit adapter (duck-type)
└── agent/orbit_agent.py     — OrbitAgent, OrbitChain (SHA-256 audit trail)
```

---

## Orbit Phase FSM

```
INJECTION → ELLIPTICAL → CIRCULARIZING → CIRCULAR
         → MANEUVERING → STATION_KEEPING → NOMINAL
         → DEORBIT_BURN → REENTRY
         (anytime) → ABORT
```

---

## Ω Health Score (5 Components)

| Component | Weight | Description |
|-----------|--------|-------------|
| `ω_periapsis` | 0.30 | Periapsis altitude ≥ 80km (atmosphere boundary) |
| `ω_energy` | 0.25 | Specific energy negative (bound orbit) |
| `ω_eccentricity` | 0.20 | Eccentricity within target range |
| `ω_inclination` | 0.15 | Inclination error from target |
| `ω_coverage` | 0.10 | Period / altitude mission suitability |

**verdict**: `NOMINAL` (Ω≥0.90) / `STABLE` (≥0.75) / `DEGRADED` (≥0.55) / `CRITICAL`

---

## Supported Maneuvers

| Maneuver | Description | ΔV Reference |
|----------|-------------|--------------|
| **Circularization** | Ellipse → circle at apoapsis | Tens to hundreds m/s |
| **Hohmann Transfer** | Optimal transfer between two circular orbits | LEO↔GEO ≈ 3.9 km/s |
| **Plane Change** | Inclination adjustment | 2·v·sin(Δi/2) |
| **Deorbit Burn** | Lower periapsis into atmosphere | Tens to hundreds m/s |

---

## J2 Perturbation

With `use_j2=True`, includes **RAAN precession and argument of periapsis drift** significant in LEO:

```
dΩ/dt = −(3/2)·n·J2·(R⊕/p)²·cos(i)    ← westward RAAN drift
dω/dt = (3/4)·n·J2·(R⊕/p)²·(5cos²i−1)  ← periapsis drift
```

---

## Tests

```bash
cd Lucifer_Engine
python -m pytest tests/ -v
```

Current: **133 passed**

| Section | Coverage |
|---------|----------|
| §1 | Data contracts (StateVector, KeplerElements, MissionProfile) |
| §2 | Kepler mechanics (conversion, propagation, Vis-Viva) |
| §3 | Orbital maneuvers (circularize, Hohmann, plane change, deorbit, budget) |
| §4 | Orbit health Ω scoring |
| §5 | Propagator (Kepler, J2, single step) |
| §6 | Rocket_Spirit bridge (dict, duck-type, tuple) |
| §7 | OrbitAgent integration + OrbitChain SHA-256 |

---

## Roadmap

- `v0.1.0`: current — Kepler propagation, maneuver planning, Ω health, Rocket_Spirit bridge
- `v0.2.0`: TLE input support (Two-Line Element)
- `v0.3.0`: Monte Carlo ΔV dispersion analysis
- `v0.4.0`: Reusable vehicle return trajectory (aerobraking, retropropulsion)
- `v0.5.0`: Multi-satellite constellation deployment

---

## Ecosystem Position

```
[Wheelchair] → WTS morph → TAM/StarScream → Rocket_Spirit → Lucifer_Engine
                                                  (launch→orbit insertion)  (orbit ops)
```

`Lucifer_Engine` is the **v0.2.0 integration target** for `Rocket_Spirit`.
