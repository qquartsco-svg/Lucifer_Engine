"""
Lucifer_Engine — 케플러 궤도 역학 모듈

상태 벡터 ↔ 케플러 요소 변환 (Lambert, Gauss 방법 아님 — 단순 r·v → elements).
stdlib + math 전용. 외부 의존성 없음.

참고:
  Bate, Mueller, White, "Fundamentals of Astrodynamics", 1971
  Vallado, "Fundamentals of Astrodynamics and Applications", 4th ed.
"""

from __future__ import annotations

import math
from typing import Tuple

from lucifer_engine.contracts.schemas import (
    KeplerElements,
    MU_EARTH,
    R_EARTH,
    StateVector,
)

# 수치 안전 임계값
_EPS = 1e-12
_TWO_PI = 2.0 * math.pi


# ---------------------------------------------------------------------------
# A. 상태 벡터 → 케플러 요소
# ---------------------------------------------------------------------------

def state_to_elements(sv: StateVector) -> KeplerElements:
    """
    3D 상태 벡터(r, v) → 고전 케플러 6요소.

    좌표계: ECI 근사 (발사장 중심 직교, z=Up)
    반환: KeplerElements (a, e, i, raan, argp, nu)
    """
    # 위치·속도 성분
    rx, ry, rz = sv.x_m, sv.y_m, sv.z_m + R_EARTH   # 지구 중심 기준
    vx, vy, vz = sv.vx_ms, sv.vy_ms, sv.vz_ms

    r_mag = math.sqrt(rx*rx + ry*ry + rz*rz)
    v_mag = math.sqrt(vx*vx + vy*vy + vz*vz)

    # 특이 케이스 방지
    if r_mag < _EPS:
        return _zero_elements()

    # 1. 각운동량 벡터 h = r × v
    hx = ry*vz - rz*vy
    hy = rz*vx - rx*vz
    hz = rx*vy - ry*vx
    h_mag = math.sqrt(hx*hx + hy*hy + hz*hz)

    # 2. 이심률 벡터 e = (v×h)/μ − r̂
    #    e = [(v²−μ/r)r − (r·v)v] / μ
    r_dot_v = rx*vx + ry*vy + rz*vz
    mu = MU_EARTH
    ex = ((v_mag*v_mag - mu/r_mag)*rx - r_dot_v*vx) / mu
    ey = ((v_mag*v_mag - mu/r_mag)*ry - r_dot_v*vy) / mu
    ez = ((v_mag*v_mag - mu/r_mag)*rz - r_dot_v*vz) / mu
    e_mag = math.sqrt(ex*ex + ey*ey + ez*ez)

    # 3. 비 에너지 ε = v²/2 − μ/r
    eps = 0.5*v_mag*v_mag - mu/r_mag

    # 4. 반장축 a = −μ/(2ε)  (타원: eps<0, a>0)
    if abs(eps) < _EPS:
        a = float("inf")   # 포물선 (탈출 임계)
    else:
        a = -mu / (2.0 * eps)

    # 5. 경사각 i = arccos(hz/h)
    if h_mag < _EPS:
        i = 0.0
    else:
        i = math.acos(max(-1.0, min(1.0, hz / h_mag)))

    # 6. 승교점 벡터 n = k × h  (k = z축 단위벡터)
    nx = -hy   # (0,0,1) × (hx,hy,hz) = (-hy, hx, 0)
    ny =  hx
    n_mag = math.sqrt(nx*nx + ny*ny)

    # 7. 승교점 적경 RAAN (Ω)
    if n_mag < _EPS:
        raan = 0.0
    else:
        raan = math.acos(max(-1.0, min(1.0, nx / n_mag)))
        if ny < 0:
            raan = _TWO_PI - raan

    # 8. 근지점 편각 ω
    if n_mag < _EPS or e_mag < _EPS:
        argp = 0.0
    else:
        n_dot_e = nx*ex + ny*ey    # + 0*ez (nz=0)
        cos_argp = max(-1.0, min(1.0, n_dot_e / (n_mag * e_mag)))
        argp = math.acos(cos_argp)
        if ez < 0:
            argp = _TWO_PI - argp

    # 9. 진근점 이각 ν
    if e_mag < _EPS:
        # 원 궤도 — ν 를 위도 편각(u)으로 대체
        if n_mag < _EPS:
            nu = 0.0
        else:
            r_hat_x = rx / r_mag
            r_hat_y = ry / r_mag
            cos_nu = max(-1.0, min(1.0, (nx*r_hat_x + ny*r_hat_y) / n_mag))
            nu = math.acos(cos_nu)
            if rz < 0:
                nu = _TWO_PI - nu
    else:
        e_dot_r = ex*rx + ey*ry + ez*rz
        cos_nu = max(-1.0, min(1.0, e_dot_r / (e_mag * r_mag)))
        nu = math.acos(cos_nu)
        if r_dot_v < 0:
            nu = _TWO_PI - nu

    return KeplerElements(
        a=a,
        e=e_mag,
        i=i,
        raan=raan,
        argp=argp,
        nu=nu,
    )


# ---------------------------------------------------------------------------
# B. 케플러 요소 → 상태 벡터 (역변환)
# ---------------------------------------------------------------------------

def elements_to_state(
    elem: KeplerElements,
    t_s: float = 0.0,
    mass_kg: float = 0.0,
) -> StateVector:
    """
    케플러 요소 → 직교 상태 벡터 (ECI 근사).
    """
    a, e, i = elem.a, elem.e, elem.i
    raan, argp, nu = elem.raan, elem.argp, elem.nu
    mu = MU_EARTH

    if a <= 0 or e >= 1.0:
        # 탈출 궤도 — 근사 처리
        return StateVector(t_s=t_s, mass_kg=mass_kg)

    p = a * (1.0 - e*e)   # 반통경 (semi-latus rectum)
    if p < _EPS:
        return StateVector(t_s=t_s, mass_kg=mass_kg)

    r = p / (1.0 + e * math.cos(nu))  # 극좌표 반지름
    h = math.sqrt(mu * p)

    # 궤도면 좌표 (PQW)
    cos_nu, sin_nu = math.cos(nu), math.sin(nu)
    r_pqw_x = r * cos_nu
    r_pqw_y = r * sin_nu
    v_pqw_x = -math.sqrt(mu/p) * sin_nu
    v_pqw_y =  math.sqrt(mu/p) * (e + cos_nu)

    # 회전 행렬 PQW → ECI (Euler 3-1-3: -raan, -i, -argp)
    cos_r, sin_r = math.cos(raan), math.sin(raan)
    cos_i, sin_i = math.cos(i),    math.sin(i)
    cos_a, sin_a = math.cos(argp),  math.sin(argp)

    # R = Rz(-raan) · Rx(-i) · Rz(-argp)
    r11 =  cos_r*cos_a - sin_r*sin_a*cos_i
    r12 = -cos_r*sin_a - sin_r*cos_a*cos_i
    r21 =  sin_r*cos_a + cos_r*sin_a*cos_i
    r22 = -sin_r*sin_a + cos_r*cos_a*cos_i
    r31 =  sin_a*sin_i
    r32 =  cos_a*sin_i

    # ECI 위치 (지구 중심 기준)
    rx_eci = r11*r_pqw_x + r12*r_pqw_y
    ry_eci = r21*r_pqw_x + r22*r_pqw_y
    rz_eci = r31*r_pqw_x + r32*r_pqw_y

    # ECI 속도
    vx_eci = r11*v_pqw_x + r12*v_pqw_y
    vy_eci = r21*v_pqw_x + r22*v_pqw_y
    vz_eci = r31*v_pqw_x + r32*v_pqw_y

    # ECI → 발사장 중심 (z = 지표 고도)
    altitude_m = math.sqrt(rx_eci**2 + ry_eci**2 + rz_eci**2) - R_EARTH

    return StateVector(
        x_m=rx_eci,
        y_m=ry_eci,
        z_m=altitude_m,
        vx_ms=vx_eci,
        vy_ms=vy_eci,
        vz_ms=vz_eci,
        t_s=t_s,
        mass_kg=mass_kg,
    )


# ---------------------------------------------------------------------------
# C. 케플러 전파 (시간 이동)
# ---------------------------------------------------------------------------

def propagate_kepler(elem: KeplerElements, dt_s: float) -> KeplerElements:
    """
    케플러 2체 방정식으로 dt_s 이후 케플러 요소를 반환.
    a, e, i, raan, argp 는 보존 (섭동 없음).
    nu만 갱신 (평균 이상 → 이심 이상 → 진 이상 변환).
    """
    if elem.e >= 1.0 or elem.a <= 0:
        return elem   # 탈출 궤도는 전파 미지원

    n = elem.mean_motion_rad_s          # 평균 운동 (rad/s)

    # 현재 진 이상 → 이심 이상 E
    nu = elem.nu
    e  = elem.e
    E0 = _true_to_eccentric_anomaly(nu, e)

    # 평균 이상 M0 = E0 − e·sin(E0)
    M0 = E0 - e * math.sin(E0)

    # dt 후 평균 이상
    M1 = (M0 + n * dt_s) % _TWO_PI

    # 이심 이상 E1 (Kepler 방정식 Newton 풀이)
    E1 = _solve_kepler(M1, e)

    # 이심 이상 → 진 이상
    nu1 = _eccentric_to_true_anomaly(E1, e)

    import dataclasses
    return dataclasses.replace(elem, nu=nu1)


def _true_to_eccentric_anomaly(nu: float, e: float) -> float:
    """진 이상 ν → 이심 이상 E."""
    tan_half = math.tan(nu / 2.0)
    factor = math.sqrt((1.0 - e) / (1.0 + e + _EPS))
    E = 2.0 * math.atan(factor * tan_half)
    return E % _TWO_PI


def _eccentric_to_true_anomaly(E: float, e: float) -> float:
    """이심 이상 E → 진 이상 ν."""
    cos_nu = (math.cos(E) - e) / (1.0 - e * math.cos(E) + _EPS)
    sin_nu = (math.sqrt(1.0 - e*e) * math.sin(E)) / (1.0 - e * math.cos(E) + _EPS)
    return math.atan2(sin_nu, cos_nu) % _TWO_PI


def _solve_kepler(M: float, e: float, max_iter: int = 50) -> float:
    """Newton-Raphson으로 케플러 방정식 M = E − e·sin(E) 풀이."""
    E = M  # 초기 추정
    for _ in range(max_iter):
        dE = (M - E + e * math.sin(E)) / (1.0 - e * math.cos(E) + _EPS)
        E += dE
        if abs(dE) < 1e-12:
            break
    return E % _TWO_PI


# ---------------------------------------------------------------------------
# D. 순환 유틸리티
# ---------------------------------------------------------------------------

def circular_velocity_ms(altitude_m: float) -> float:
    """고도 altitude_m 에서 원 궤도 속도 (m/s)."""
    r = R_EARTH + altitude_m
    return math.sqrt(MU_EARTH / r)


def orbital_period_s(altitude_m: float) -> float:
    """고도 altitude_m 원 궤도 주기 (s)."""
    r = R_EARTH + altitude_m
    return 2.0 * math.pi * math.sqrt(r**3 / MU_EARTH)


def escape_velocity_ms(altitude_m: float) -> float:
    """고도 altitude_m 에서 탈출 속도 (m/s)."""
    r = R_EARTH + altitude_m
    return math.sqrt(2.0 * MU_EARTH / r)


def vis_viva_ms(r_m: float, a_m: float) -> float:
    """Vis-Viva 방정식: v = √(μ(2/r − 1/a))."""
    return math.sqrt(max(0.0, MU_EARTH * (2.0/r_m - 1.0/a_m)))


def _zero_elements() -> KeplerElements:
    return KeplerElements(a=0.0, e=0.0, i=0.0, raan=0.0, argp=0.0, nu=0.0)
