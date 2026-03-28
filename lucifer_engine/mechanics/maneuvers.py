"""
Lucifer_Engine — 궤도 기동 계획 모듈

지원 기동:
  1. 원형화 번 (Circularization) — 원지점에서 타원→원 전환
  2. 호만 전이 (Hohmann Transfer) — 두 원 궤도 사이 최적 전이
  3. 궤도면 변경 (Plane Change) — 경사각 변경
  4. 재진입 번 (Deorbit Burn) — 근지점을 대기권 내로 낮춤

참고: Tsiolkovsky 로켓 방정식으로 ΔV → 연소 시간 변환.
"""

from __future__ import annotations

import math
from typing import Tuple

from lucifer_engine.contracts.schemas import (
    KeplerElements,
    ManeuverPlan,
    ManeuverStep,
    ManeuverType,
    MissionProfile,
    MU_EARTH,
    R_EARTH,
)
from lucifer_engine.mechanics.kepler import vis_viva_ms, circular_velocity_ms

_G0 = 9.80665   # 표준 중력 가속도 (m/s²)
_EPS = 1e-12


# ---------------------------------------------------------------------------
# 1. 원형화 번
# ---------------------------------------------------------------------------

def plan_circularization(
    elem: KeplerElements,
    mission: MissionProfile,
) -> ManeuverPlan:
    """
    타원 궤도 원지점(apoapsis)에서 원형화 번 계획.

    현재 원지점 고도가 목표 고도에 가까운 경우 최적.
    반환: ManeuverPlan (단일 스텝)
    """
    ra = elem.apoapsis_m    # 원지점 거리 (지구 중심)
    rp = elem.periapsis_m   # 근지점 거리

    # 원지점에서의 현재 속도 (Vis-Viva)
    v_apo = vis_viva_ms(ra, elem.a)

    # 원지점 고도에서의 원 궤도 속도
    v_circ = math.sqrt(MU_EARTH / ra)

    delta_v = abs(v_circ - v_apo)

    burn_time_s = _tsiolkovsky_burn_time(
        delta_v, mission.isp_s,
        mission.payload_mass_kg + mission.dry_mass_kg
    )

    step = ManeuverStep(
        maneuver_type=ManeuverType.CIRCULARIZE,
        delta_v_ms=delta_v,
        burn_duration_s=burn_time_s,
        true_anomaly_rad=math.pi,   # 원지점에서 실행
        description=f"원형화 번 @ 원지점 h={ra - R_EARTH:.0f}m, ΔV={delta_v:.1f}m/s",
    )

    return ManeuverPlan(
        steps=(step,),
        total_delta_v_ms=delta_v,
        total_duration_s=burn_time_s,
        target_altitude_m=ra - R_EARTH,
    )


# ---------------------------------------------------------------------------
# 2. 호만 전이
# ---------------------------------------------------------------------------

def plan_hohmann(
    r1_m: float,
    r2_m: float,
    mission: MissionProfile,
) -> ManeuverPlan:
    """
    두 원 궤도 사이 호만 전이 계획.

    r1_m : 출발 원 궤도 반지름 (지구 중심 기준, m)
    r2_m : 도착 원 궤도 반지름 (m)
    """
    mu = MU_EARTH
    # 전이 타원 반장축
    a_trans = 0.5 * (r1_m + r2_m)

    # 1번 번 (r1 에서)
    v1_circ  = math.sqrt(mu / r1_m)
    v1_trans = vis_viva_ms(r1_m, a_trans)
    dv1 = abs(v1_trans - v1_circ)

    # 2번 번 (r2 에서)
    v2_circ  = math.sqrt(mu / r2_m)
    v2_trans = vis_viva_ms(r2_m, a_trans)
    dv2 = abs(v2_circ - v2_trans)

    total_dv = dv1 + dv2
    total_mass = mission.payload_mass_kg + mission.dry_mass_kg

    t1 = _tsiolkovsky_burn_time(dv1, mission.isp_s, total_mass)
    # 2번 번 때는 질량이 줄어 있음 (추진제 소모)
    m2 = _tsiolkovsky_remaining_mass(dv1, mission.isp_s, total_mass)
    t2 = _tsiolkovsky_burn_time(dv2, mission.isp_s, m2)

    # 전이 비행 시간 (반 궤도 주기)
    transfer_time_s = math.pi * math.sqrt(a_trans**3 / mu)

    step1 = ManeuverStep(
        maneuver_type=ManeuverType.HOHMANN,
        delta_v_ms=dv1,
        burn_duration_s=t1,
        true_anomaly_rad=0.0,
        description=f"호만 번 1: r1={r1_m - R_EARTH:.0f}m → 전이 타원 시작, ΔV={dv1:.1f}m/s",
    )
    step2 = ManeuverStep(
        maneuver_type=ManeuverType.HOHMANN,
        delta_v_ms=dv2,
        burn_duration_s=t2,
        true_anomaly_rad=math.pi,
        description=f"호만 번 2: 전이 타원 → r2={r2_m - R_EARTH:.0f}m 원 궤도 진입, ΔV={dv2:.1f}m/s",
    )

    return ManeuverPlan(
        steps=(step1, step2),
        total_delta_v_ms=total_dv,
        total_duration_s=t1 + transfer_time_s + t2,
        target_altitude_m=r2_m - R_EARTH,
    )


# ---------------------------------------------------------------------------
# 3. 궤도면 변경
# ---------------------------------------------------------------------------

def plan_plane_change(
    elem: KeplerElements,
    target_inclination_rad: float,
    mission: MissionProfile,
) -> ManeuverPlan:
    """
    경사각 변경 기동 ΔV = 2·v·sin(Δi/2).
    원 궤도 가정. 최적 위치: 적도 교차점.
    """
    di = abs(target_inclination_rad - elem.i)
    if di < 1e-6:
        return ManeuverPlan()   # 변경 불요

    v = elem.circular_velocity_ms
    delta_v = 2.0 * v * math.sin(di / 2.0)

    burn_time_s = _tsiolkovsky_burn_time(
        delta_v, mission.isp_s,
        mission.payload_mass_kg + mission.dry_mass_kg
    )

    step = ManeuverStep(
        maneuver_type=ManeuverType.PLANE_CHANGE,
        delta_v_ms=delta_v,
        burn_duration_s=burn_time_s,
        description=f"궤도면 변경 Δi={math.degrees(di):.2f}°, ΔV={delta_v:.1f}m/s",
    )

    return ManeuverPlan(
        steps=(step,),
        total_delta_v_ms=delta_v,
        total_duration_s=burn_time_s,
        target_inclination_rad=target_inclination_rad,
    )


# ---------------------------------------------------------------------------
# 4. 재진입 번
# ---------------------------------------------------------------------------

def plan_deorbit(
    elem: KeplerElements,
    target_periapsis_altitude_m: float,
    mission: MissionProfile,
) -> ManeuverPlan:
    """
    근지점을 target_periapsis_altitude_m 로 낮추는 역추진 번.
    현재 원 궤도 → 재진입 타원.
    """
    r_current = elem.apoapsis_m   # 현재 원 궤도 = 원지점
    r_peri    = R_EARTH + target_periapsis_altitude_m

    # 재진입 타원 반장축
    a_deorbit = 0.5 * (r_current + r_peri)
    v_circ    = math.sqrt(MU_EARTH / r_current)
    v_deorbit = vis_viva_ms(r_current, a_deorbit)
    delta_v   = abs(v_circ - v_deorbit)   # 역방향 번

    burn_time_s = _tsiolkovsky_burn_time(
        delta_v, mission.isp_s,
        mission.payload_mass_kg + mission.dry_mass_kg
    )

    step = ManeuverStep(
        maneuver_type=ManeuverType.DEORBIT,
        delta_v_ms=delta_v,
        burn_duration_s=burn_time_s,
        description=(
            f"재진입 번: 근지점 → {target_periapsis_altitude_m/1000:.1f}km, "
            f"ΔV={delta_v:.1f}m/s"
        ),
    )

    return ManeuverPlan(
        steps=(step,),
        total_delta_v_ms=delta_v,
        total_duration_s=burn_time_s,
        target_altitude_m=target_periapsis_altitude_m,
    )


# ---------------------------------------------------------------------------
# 5. ΔV 예산 확인
# ---------------------------------------------------------------------------

def delta_v_budget(mission: MissionProfile, *plans: ManeuverPlan) -> dict:
    """
    임무 ΔV 예산 사용량 요약.
    """
    used = sum(p.total_delta_v_ms for p in plans)
    available = mission.max_delta_v_ms
    remaining = available - used
    return {
        "available_ms": available,
        "used_ms": used,
        "remaining_ms": remaining,
        "margin_pct": (remaining / available * 100.0) if available > 0 else 0.0,
        "budget_ok": remaining >= 0.0,
    }


# ---------------------------------------------------------------------------
# 내부 유틸리티 — Tsiolkovsky
# ---------------------------------------------------------------------------

def _tsiolkovsky_burn_time(
    delta_v_ms: float,
    isp_s: float,
    wet_mass_kg: float,
    thrust_n: float = 2_000.0,   # 기본 상단 엔진 추력 (N)
) -> float:
    """
    ΔV와 비추력으로 연소 시간 추정 (Tsiolkovsky 기반).
    실제 스로틀·압력 모델 없이 평균 추력 가정.
    """
    if isp_s <= 0 or wet_mass_kg <= 0 or thrust_n <= 0:
        return 0.0
    ve = isp_s * _G0   # 유효 배기 속도 (m/s)
    # 질량 비 mp/m0 = 1 − exp(−ΔV/ve)
    mass_ratio = 1.0 - math.exp(-delta_v_ms / (ve + 1e-12))
    prop_mass_kg = wet_mass_kg * mass_ratio
    # 연소 시간 ≈ mp × ve / F
    return prop_mass_kg * ve / (thrust_n + 1e-12)


def _tsiolkovsky_remaining_mass(
    delta_v_ms: float,
    isp_s: float,
    wet_mass_kg: float,
) -> float:
    """ΔV 후 남은 질량 (건 + 잔류 추진제)."""
    ve = isp_s * _G0
    return wet_mass_kg * math.exp(-delta_v_ms / (ve + 1e-12))
