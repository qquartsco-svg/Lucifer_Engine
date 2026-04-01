"""
Lucifer_Engine -> OrbitalCore_Engine bridge.

장기적으로 Lucifer의 orbital math ownership을 OrbitalCore로 수렴시키기 위한
얇은 adapter 레이어다. OrbitalCore가 없으면 기존 Lucifer mechanics로 fallback 한다.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Any

from lucifer_engine.contracts.schemas import (
    KeplerElements,
    ManeuverPlan,
    ManeuverStep,
    ManeuverType,
    MissionProfile,
    OrbitHealthReport,
    OrbitPhase,
    PropagationResult,
    R_EARTH,
    StateVector,
)


def _ensure_orbital_core_importable() -> bool:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "OrbitalCore_Engine"
        if (candidate / "orbital_core").is_dir():
            path = str(candidate)
            if path not in sys.path:
                sys.path.insert(0, path)
            return True
        candidate = parent / "_staging" / "OrbitalCore_Engine"
        if (candidate / "orbital_core").is_dir():
            path = str(candidate)
            if path not in sys.path:
                sys.path.insert(0, path)
            return True
    return False


def orbital_core_available() -> bool:
    if not _ensure_orbital_core_importable():
        return False
    try:
        import orbital_core  # noqa: F401
        return True
    except Exception:
        return False


def _to_lucifer_target(target: Any) -> KeplerElements | None:
    if target is None:
        return None
    return KeplerElements(
        a=float(target.semi_major_axis_m),
        e=float(target.eccentricity),
        i=float(target.inclination_rad),
        raan=float(target.raan_rad),
        argp=float(target.arg_of_perigee_rad),
        nu=0.0,
    )


def _to_orbital_core_elements(elem: KeplerElements, *, epoch_s: float = 0.0) -> Any:
    from orbital_core.contracts import OrbitalElements

    return OrbitalElements(
        semi_major_axis_m=float(elem.a),
        eccentricity=float(elem.e),
        inclination_rad=float(elem.i),
        raan_rad=float(elem.raan),
        arg_of_perigee_rad=float(elem.argp),
        mean_anomaly_rad=0.0,
        epoch_s=float(epoch_s),
    )


def _to_lucifer_state(state: Any, *, mass_kg: float) -> StateVector:
    pos = tuple(float(x) for x in state.pos_eci_m)
    vel = tuple(float(x) for x in state.vel_eci_ms)
    altitude_m = float(state.altitude_m)
    return StateVector(
        x_m=pos[0],
        y_m=pos[1],
        z_m=altitude_m,
        vx_ms=vel[0],
        vy_ms=vel[1],
        vz_ms=vel[2],
        t_s=float(state.time_s),
        mass_kg=float(mass_kg),
    )


def state_to_elements_bridge(sv: StateVector) -> KeplerElements:
    try:
        if orbital_core_available():
            from orbital_core.kepler import state_vector_to_elements

            pos = (float(sv.x_m), float(sv.y_m), float(sv.z_m + R_EARTH))
            vel = (float(sv.vx_ms), float(sv.vy_ms), float(sv.vz_ms))
            elem = state_vector_to_elements(pos, vel)
            return _to_lucifer_target(elem) or KeplerElements(
                a=R_EARTH + max(0.0, sv.altitude_m),
                e=0.0,
                i=0.0,
                raan=0.0,
                argp=0.0,
                nu=0.0,
            )
    except Exception:
        pass

    from lucifer_engine.mechanics.kepler import state_to_elements
    return state_to_elements(sv)


def elements_to_state_bridge(
    elem: KeplerElements,
    *,
    t_s: float = 0.0,
    mass_kg: float = 0.0,
) -> StateVector:
    try:
        if orbital_core_available():
            from orbital_core.kepler import elements_to_state_vector

            oc_elements = _to_orbital_core_elements(elem, epoch_s=t_s)
            pos, vel = elements_to_state_vector(oc_elements)
            radius_m = math.sqrt(sum(float(x) * float(x) for x in pos))
            altitude_m = radius_m - R_EARTH
            return StateVector(
                x_m=float(pos[0]),
                y_m=float(pos[1]),
                z_m=float(altitude_m),
                vx_ms=float(vel[0]),
                vy_ms=float(vel[1]),
                vz_ms=float(vel[2]),
                t_s=float(t_s),
                mass_kg=float(mass_kg),
            )
    except Exception:
        pass

    from lucifer_engine.mechanics.kepler import elements_to_state
    return elements_to_state(elem, t_s=t_s, mass_kg=mass_kg)


def plan_hohmann_bridge(
    r1_m: float,
    r2_m: float,
    mission: MissionProfile,
) -> ManeuverPlan:
    try:
        if orbital_core_available():
            from orbital_core.maneuver import hohmann_transfer

            plan = hohmann_transfer(r1_m, r2_m)
            steps = tuple(
                ManeuverStep(
                    maneuver_type=ManeuverType.HOHMANN,
                    delta_v_ms=float(b["delta_v_ms"]),
                    burn_duration_s=0.0,
                    true_anomaly_rad=0.0 if idx == 0 else math.pi,
                    description=f"OrbitalCore bridge hohmann burn {idx + 1}",
                )
                for idx, b in enumerate(plan.burns)
            )
            total_duration_s = float(plan.burns[-1]["time_s"]) if plan.burns else 0.0
            return ManeuverPlan(
                steps=steps,
                total_delta_v_ms=float(plan.delta_v_total_ms),
                total_duration_s=total_duration_s,
                target_altitude_m=r2_m - R_EARTH,
                target_inclination_rad=0.0,
            )
    except Exception:
        pass

    from lucifer_engine.mechanics.maneuvers import plan_hohmann
    return plan_hohmann(r1_m, r2_m, mission)


def plan_circularization_bridge(
    elem: KeplerElements,
    mission: MissionProfile,
) -> ManeuverPlan:
    try:
        if orbital_core_available():
            from orbital_core.contracts import OrbitalElements
            from orbital_core.maneuver import circularization_burn

            target = OrbitalElements(
                semi_major_axis_m=float(elem.a),
                eccentricity=float(elem.e),
                inclination_rad=float(elem.i),
                raan_rad=float(elem.raan),
                arg_of_perigee_rad=float(elem.argp),
                mean_anomaly_rad=0.0,
            )
            plan = circularization_burn(target)
            steps = tuple(
                ManeuverStep(
                    maneuver_type=ManeuverType.CIRCULARIZE,
                    delta_v_ms=float(b["delta_v_ms"]),
                    burn_duration_s=0.0,
                    true_anomaly_rad=math.pi,
                    description="OrbitalCore bridge circularization",
                )
                for b in plan.burns
            )
            return ManeuverPlan(
                steps=steps,
                total_delta_v_ms=float(plan.delta_v_total_ms),
                total_duration_s=float(plan.burns[-1]["time_s"]) if plan.burns else 0.0,
                target_altitude_m=(plan.target_orbit.semi_major_axis_m - R_EARTH) if plan.target_orbit else elem.apoapsis_altitude_m,
                target_inclination_rad=float(elem.i),
            )
    except Exception:
        pass

    from lucifer_engine.mechanics.maneuvers import plan_circularization
    return plan_circularization(elem, mission)


def plan_deorbit_bridge(
    elem: KeplerElements,
    target_periapsis_altitude_m: float,
    mission: MissionProfile,
) -> ManeuverPlan:
    try:
        if orbital_core_available():
            from orbital_core.contracts import OrbitalElements
            from orbital_core.maneuver import deorbit_burn

            target = OrbitalElements(
                semi_major_axis_m=float(elem.a),
                eccentricity=float(elem.e),
                inclination_rad=float(elem.i),
                raan_rad=float(elem.raan),
                arg_of_perigee_rad=float(elem.argp),
                mean_anomaly_rad=0.0,
            )
            plan = deorbit_burn(target, target_periapsis_altitude_m)
            steps = tuple(
                ManeuverStep(
                    maneuver_type=ManeuverType.DEORBIT,
                    delta_v_ms=float(b["delta_v_ms"]),
                    burn_duration_s=0.0,
                    true_anomaly_rad=0.0,
                    description="OrbitalCore bridge deorbit",
                )
                for b in plan.burns
            )
            return ManeuverPlan(
                steps=steps,
                total_delta_v_ms=float(plan.delta_v_total_ms),
                total_duration_s=float(plan.burns[-1]["time_s"]) if plan.burns else 0.0,
                target_altitude_m=target_periapsis_altitude_m,
                target_inclination_rad=float(elem.i),
            )
    except Exception:
        pass

    from lucifer_engine.mechanics.maneuvers import plan_deorbit
    return plan_deorbit(elem, target_periapsis_altitude_m, mission)


def step_propagate_bridge(
    elem: KeplerElements,
    sv: StateVector,
    dt_s: float,
    phase: OrbitPhase,
    use_j2: bool = False,
) -> PropagationResult:
    try:
        if orbital_core_available():
            from orbital_core.adapter import OrbitalAdapter
            from lucifer_engine.health.orbit_health import assess_orbit_health
            from lucifer_engine.mechanics.kepler import state_to_elements

            adapter = OrbitalAdapter()
            oc_elements = _to_orbital_core_elements(elem, epoch_s=sv.t_s)
            oc_state = adapter.from_elements(oc_elements)
            oc_state = adapter.propagate(oc_state, dt_s, with_j2=use_j2, with_drag=False)

            new_sv = _to_lucifer_state(oc_state, mass_kg=sv.mass_kg)
            new_elem = state_to_elements(new_sv)
            health = assess_orbit_health(new_elem, phase=phase)

            return PropagationResult(
                t_s=float(oc_state.time_s),
                state=new_sv,
                elements=new_elem,
                phase=phase,
                health=health,
                event="orbital_core_bridge_propagation",
            )
    except Exception:
        pass

    from lucifer_engine.mechanics.propagator import step_propagate
    return step_propagate(elem, sv, dt_s, phase=phase, use_j2=use_j2)
