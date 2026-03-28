"""
Lucifer_Engine — 궤도 건강도 평가 (Ω 스코어)

5개 컴포넌트:
  ω_periapsis   — 근지점이 대기권(80km) 이상
  ω_energy      — 비 에너지가 음수(타원/원 궤도)
  ω_eccentricity — 이심률이 원 궤도 기준 허용 범위
  ω_inclination  — 경사각이 목표 허용 범위
  ω_coverage     — 주기·고도 조합 임무 적합성

가중 합산:
  Ω_total = 0.30·ω_p + 0.25·ω_e + 0.20·ω_ecc + 0.15·ω_i + 0.10·ω_cov
"""

from __future__ import annotations

import math

from lucifer_engine.contracts.schemas import (
    KeplerElements,
    OrbitHealthReport,
    OrbitPhase,
    R_EARTH,
)

# ---------------------------------------------------------------------------
# 설계 상수
# ---------------------------------------------------------------------------
_MIN_PERIAPSIS_ALT_M  = 80_000.0    # 대기권 상한 (80km) — 이하면 재진입
_SAFE_PERIAPSIS_ALT_M = 150_000.0   # 안전 근지점 고도 (150km)
_LEO_MIN_ALT_M        = 200_000.0   # LEO 최저 고도 (200km)
_LEO_MAX_ALT_M        = 2_000_000.0 # LEO 최고 고도 (2,000km)
_MAX_SAFE_ECC         = 0.05        # 원 궤도 허용 이심률
_TARGET_INC_RAD       = math.radians(28.5)   # 기본 목표 경사각 (케네디 위도)
_INC_TOLERANCE_RAD    = math.radians(5.0)    # ±5° 허용

# 가중치
_W_PERI  = 0.30
_W_ENRG  = 0.25
_W_ECC   = 0.20
_W_INC   = 0.15
_W_COV   = 0.10


def assess_orbit_health(
    elem: KeplerElements,
    phase: OrbitPhase = OrbitPhase.CIRCULAR,
    target_inclination_rad: float = _TARGET_INC_RAD,
    target_altitude_m: float = 400_000.0,
) -> OrbitHealthReport:
    """
    케플러 요소로 궤도 건강도 Ω 판정.

    Parameters
    ----------
    elem                  : 현재 케플러 요소
    phase                 : 현재 궤도 단계
    target_inclination_rad: 목표 경사각 (rad)
    target_altitude_m     : 목표 고도 (m)

    Returns
    -------
    OrbitHealthReport
    """
    blockers: list[str] = []
    evidence: dict = {}

    peri_alt  = elem.periapsis_altitude_m
    apo_alt   = elem.apoapsis_altitude_m
    ecc       = elem.e
    inc       = elem.i

    # ------------------------------------------------------------------
    # ω_periapsis — 근지점 고도 기준
    # ------------------------------------------------------------------
    if peri_alt < _MIN_PERIAPSIS_ALT_M:
        omega_periapsis = 0.0
        blockers.append("periapsis_below_atmosphere")
    elif peri_alt < _SAFE_PERIAPSIS_ALT_M:
        # 80km~150km 선형 보간
        omega_periapsis = (peri_alt - _MIN_PERIAPSIS_ALT_M) / (
            _SAFE_PERIAPSIS_ALT_M - _MIN_PERIAPSIS_ALT_M
        ) * 0.5
    elif peri_alt < _LEO_MIN_ALT_M:
        # 150km~200km
        omega_periapsis = 0.5 + (peri_alt - _SAFE_PERIAPSIS_ALT_M) / (
            _LEO_MIN_ALT_M - _SAFE_PERIAPSIS_ALT_M
        ) * 0.4
    else:
        omega_periapsis = 1.0

    evidence["periapsis_alt_km"] = round(peri_alt / 1000.0, 2)

    # ------------------------------------------------------------------
    # ω_energy — 비 에너지 (음수 = 타원/원, 양수 = 탈출)
    # ------------------------------------------------------------------
    if ecc >= 1.0 or elem.a <= 0:
        omega_energy = 0.0
        blockers.append("escape_trajectory")
    else:
        # 에너지 마진: 얼마나 안정적으로 속박되어 있는지
        # a 가 클수록(높은 궤도) 에너지 절댓값 작음 → 정규화 필요
        # 기준: LEO(400km) a 에너지를 1.0 기준
        a_leo  = R_EARTH + 400_000.0
        eps_leo = -9.80665 * 6_371_000.0**2 / (2.0 * a_leo)  # 근사
        # 단순화: a 가 합리적 LEO 범위 내면 1.0
        if _LEO_MIN_ALT_M <= elem.a - R_EARTH <= _LEO_MAX_ALT_M:
            omega_energy = 1.0
        elif elem.a - R_EARTH < _LEO_MIN_ALT_M:
            omega_energy = max(0.0, (elem.a - R_EARTH) / _LEO_MIN_ALT_M)
        else:
            # HEO 또는 GTO — 에너지 기준 감점 없음
            omega_energy = 0.9

    # ------------------------------------------------------------------
    # ω_eccentricity — 이심률
    # ------------------------------------------------------------------
    if ecc >= 1.0:
        omega_eccentricity = 0.0
    elif ecc <= 0.001:
        omega_eccentricity = 1.0     # 완벽 원 궤도
    elif ecc <= _MAX_SAFE_ECC:
        # 0.001~0.05 선형
        omega_eccentricity = 1.0 - (ecc / _MAX_SAFE_ECC) * 0.3
    elif ecc <= 0.3:
        # 타원 궤도 — 기동 중이면 허용
        omega_eccentricity = 0.7 - (ecc - _MAX_SAFE_ECC) / (0.3 - _MAX_SAFE_ECC) * 0.4
        if phase in (OrbitPhase.ELLIPTICAL, OrbitPhase.CIRCULARIZING, OrbitPhase.INJECTION):
            omega_eccentricity = max(omega_eccentricity, 0.5)
    else:
        omega_eccentricity = max(0.1, 0.3 - ecc * 0.5)

    evidence["eccentricity"] = round(ecc, 5)

    # ------------------------------------------------------------------
    # ω_inclination — 목표 경사각 오차
    # ------------------------------------------------------------------
    di = abs(inc - target_inclination_rad)
    if di <= _INC_TOLERANCE_RAD:
        omega_inclination = 1.0
    elif di <= math.radians(15.0):
        omega_inclination = 1.0 - (di - _INC_TOLERANCE_RAD) / math.radians(10.0) * 0.5
    else:
        omega_inclination = max(0.2, 0.5 - (di - math.radians(15.0)) / math.pi * 0.3)

    evidence["inclination_deg"] = round(math.degrees(inc), 2)
    evidence["inc_error_deg"]   = round(math.degrees(di), 2)

    # ------------------------------------------------------------------
    # ω_coverage — 임무 커버리지 (주기·고도)
    # ------------------------------------------------------------------
    period_s = elem.period_s
    if 80 * 60 <= period_s <= 130 * 60:    # LEO 주기 범위 80~130분
        omega_coverage = 1.0
    elif 60 * 60 <= period_s <= 24 * 3600:  # MEO~GEO
        omega_coverage = 0.8
    elif period_s > 0:
        omega_coverage = 0.5
    else:
        omega_coverage = 0.0

    evidence["period_min"] = round(period_s / 60.0, 1)
    evidence["apoapsis_alt_km"] = round(apo_alt / 1000.0, 2)

    # ------------------------------------------------------------------
    # Ω_total 가중 합산
    # ------------------------------------------------------------------
    omega_total = (
        _W_PERI * omega_periapsis  +
        _W_ENRG * omega_energy     +
        _W_ECC  * omega_eccentricity +
        _W_INC  * omega_inclination  +
        _W_COV  * omega_coverage
    )

    # ------------------------------------------------------------------
    # verdict 판정
    # ------------------------------------------------------------------
    if blockers:
        verdict = "CRITICAL"
    elif omega_total >= 0.90:
        verdict = "NOMINAL"
    elif omega_total >= 0.75:
        verdict = "STABLE"
    elif omega_total >= 0.55:
        verdict = "DEGRADED"
    else:
        verdict = "CRITICAL"

    return OrbitHealthReport(
        omega_periapsis=round(omega_periapsis, 4),
        omega_energy=round(omega_energy, 4),
        omega_eccentricity=round(omega_eccentricity, 4),
        omega_inclination=round(omega_inclination, 4),
        omega_coverage=round(omega_coverage, 4),
        omega_total=round(omega_total, 4),
        phase=phase,
        verdict=verdict,
        blockers=tuple(blockers),
        evidence=evidence,
    )
