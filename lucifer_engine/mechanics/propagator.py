"""
Lucifer_Engine — 궤도 전파기 (Propagator)

두 가지 모드:
  1. Kepler 전파 — 섭동 없음, 빠른 장기 예측
  2. J2 섭동 전파 — RAAN 및 근지점 세차 포함 (LEO 정밀도)

외부 의존성 없음.
"""

from __future__ import annotations

import math
from typing import Iterator, List

from lucifer_engine.contracts.schemas import (
    KeplerElements,
    MU_EARTH,
    R_EARTH,
    J2,
    PropagationResult,
    OrbitPhase,
    StateVector,
)
from lucifer_engine.mechanics.kepler import (
    propagate_kepler,
    elements_to_state,
    state_to_elements,
)
from lucifer_engine.health.orbit_health import assess_orbit_health

_TWO_PI = 2.0 * math.pi


# ---------------------------------------------------------------------------
# 1. 케플러 전파 (섭동 없음)
# ---------------------------------------------------------------------------

def propagate_orbit_kepler(
    initial_elem: KeplerElements,
    initial_sv:   StateVector,
    dt_s:         float,
    steps:        int,
    phase:        OrbitPhase = OrbitPhase.CIRCULAR,
) -> List[PropagationResult]:
    """
    dt_s 간격으로 steps 회 케플러 전파.

    Parameters
    ----------
    initial_elem : 초기 케플러 요소
    initial_sv   : 초기 상태 벡터 (시간·질량 기준용)
    dt_s         : 스텝 간격 (s)
    steps        : 전파 횟수
    phase        : 궤도 단계

    Returns
    -------
    List[PropagationResult] — 각 스텝 결과
    """
    results: List[PropagationResult] = []
    elem = initial_elem
    t = initial_sv.t_s

    for step in range(steps):
        t += dt_s
        elem = propagate_kepler(elem, dt_s)
        sv = elements_to_state(elem, t_s=t, mass_kg=initial_sv.mass_kg)
        health = assess_orbit_health(elem, phase=phase)

        event = ""
        if step == 0:
            event = "propagation_start"
        elif step == steps - 1:
            event = "propagation_end"

        results.append(PropagationResult(
            t_s=t,
            state=sv,
            elements=elem,
            phase=phase,
            health=health,
            event=event,
        ))

    return results


# ---------------------------------------------------------------------------
# 2. J2 섭동 전파
# ---------------------------------------------------------------------------

def propagate_orbit_j2(
    initial_elem: KeplerElements,
    initial_sv:   StateVector,
    dt_s:         float,
    steps:        int,
    phase:        OrbitPhase = OrbitPhase.CIRCULAR,
) -> List[PropagationResult]:
    """
    J2 섭동 포함 전파 (RAAN·argp 세차 적용).

    J2 세차율 (평균 운동 기반 근사):
      dΩ/dt = −(3/2)·n·J2·(R⊕/p)²·cos(i)
      dω/dt = (3/4)·n·J2·(R⊕/p)²·(5cos²i − 1)
    """
    import dataclasses

    results: List[PropagationResult] = []
    elem = initial_elem
    t = initial_sv.t_s

    # 세차율 계산 (원 궤도 근사)
    a, e, i = elem.a, elem.e, elem.i
    if a > 0 and e < 1.0:
        p = a * (1.0 - e*e)
        n = math.sqrt(MU_EARTH / a**3)
        factor = -1.5 * n * J2 * (R_EARTH / p)**2
        d_raan_dt = factor * math.cos(i)
        d_argp_dt = factor * (-0.5) * (5.0*math.cos(i)**2 - 1.0) * (-2.0)
        # 단순화: d_argp_dt = (3/4)·n·J2·(R⊕/p)²·(5cos²i−1)
        d_argp_dt = 0.75 * n * J2 * (R_EARTH / p)**2 * (5.0*math.cos(i)**2 - 1.0)
    else:
        d_raan_dt = 0.0
        d_argp_dt = 0.0

    for step in range(steps):
        t += dt_s
        # 케플러 전파 (nu 갱신)
        elem = propagate_kepler(elem, dt_s)
        # J2 세차 적용
        new_raan = (elem.raan + d_raan_dt * dt_s) % _TWO_PI
        new_argp = (elem.argp + d_argp_dt * dt_s) % _TWO_PI
        elem = dataclasses.replace(elem, raan=new_raan, argp=new_argp)

        sv = elements_to_state(elem, t_s=t, mass_kg=initial_sv.mass_kg)
        health = assess_orbit_health(elem, phase=phase)

        event = ""
        if step == 0:
            event = "j2_propagation_start"
        elif step % 100 == 0:
            event = f"j2_step_{step}"

        results.append(PropagationResult(
            t_s=t,
            state=sv,
            elements=elem,
            phase=phase,
            health=health,
            event=event,
        ))

    return results


# ---------------------------------------------------------------------------
# 3. 단일 스텝 전파 (에이전트 루프용)
# ---------------------------------------------------------------------------

def step_propagate(
    elem: KeplerElements,
    sv:   StateVector,
    dt_s: float,
    phase: OrbitPhase,
    use_j2: bool = False,
) -> PropagationResult:
    """
    단일 스텝 전파 — OrbitAgent 루프에서 호출.
    """
    import dataclasses as dc

    if use_j2 and elem.a > 0 and elem.e < 1.0:
        p = elem.a * (1.0 - elem.e**2)
        n = math.sqrt(MU_EARTH / elem.a**3)
        factor = -1.5 * n * J2 * (R_EARTH / p)**2
        d_raan = factor * math.cos(elem.i) * dt_s
        d_argp = (0.75 * n * J2 * (R_EARTH / p)**2
                  * (5.0*math.cos(elem.i)**2 - 1.0)) * dt_s
        new_elem = propagate_kepler(elem, dt_s)
        new_elem = dc.replace(
            new_elem,
            raan=(new_elem.raan + d_raan) % _TWO_PI,
            argp=(new_elem.argp + d_argp) % _TWO_PI,
        )
    else:
        new_elem = propagate_kepler(elem, dt_s)

    t_new = sv.t_s + dt_s
    new_sv = elements_to_state(new_elem, t_s=t_new, mass_kg=sv.mass_kg)
    health = assess_orbit_health(new_elem, phase=phase)

    return PropagationResult(
        t_s=t_new,
        state=new_sv,
        elements=new_elem,
        phase=phase,
        health=health,
    )
