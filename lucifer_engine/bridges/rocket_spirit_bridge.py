"""
Lucifer_Engine — Rocket_Spirit 브리지

Rocket_Spirit(LaunchVehicle_Stack) 의 NOMINAL 출구 상태를
Lucifer_Engine StateVector로 변환하는 어댑터.

설계 원칙:
  - duck-typing: Rocket_Spirit 패키지가 없어도 동작
  - try/except ImportError 패턴
  - 외부 패키지 없이 딕셔너리 또는 duck-type 객체 모두 허용
"""

from __future__ import annotations

from typing import Any, Optional

from lucifer_engine.contracts.schemas import (
    MissionProfile,
    StateVector,
    R_EARTH,
)


def state_vector_from_rocket_spirit(
    rocket_state: Any,
    mission: Optional[MissionProfile] = None,
) -> StateVector:
    """
    Rocket_Spirit `RocketState` (또는 duck-type 객체) → Lucifer_Engine `StateVector`.

    지원 입력 형식:
      1. `RocketState` 객체 (x_m, y_m, z_m, vx_ms, vy_ms, vz_ms, total_mass_kg 속성)
      2. dict 형식 {"x_m": ..., "vx_ms": ..., ...}
      3. 숫자 tuple (x, y, z, vx, vy, vz, mass, t) — 순서 고정

    Parameters
    ----------
    rocket_state : Rocket_Spirit RocketState 또는 dict 또는 tuple
    mission      : 페이로드 질량 보정용 (없으면 total_mass_kg 그대로 사용)

    Returns
    -------
    StateVector
    """
    if isinstance(rocket_state, dict):
        x  = float(rocket_state.get("x_m",  0.0))
        y  = float(rocket_state.get("y_m",  0.0))
        z  = float(rocket_state.get("z_m",  0.0))
        vx = float(rocket_state.get("vx_ms", 0.0))
        vy = float(rocket_state.get("vy_ms", 0.0))
        vz = float(rocket_state.get("vz_ms", 0.0))
        m  = float(rocket_state.get("total_mass_kg", 0.0))
        t  = float(rocket_state.get("t_s", 0.0))
    elif isinstance(rocket_state, (tuple, list)):
        parts = list(rocket_state) + [0.0] * 8
        x, y, z, vx, vy, vz, m, t = (float(p) for p in parts[:8])
    else:
        # duck-type 객체 (RocketState 등)
        x  = float(getattr(rocket_state, "x_m",  0.0))
        y  = float(getattr(rocket_state, "y_m",  0.0))
        z  = float(getattr(rocket_state, "z_m",  getattr(rocket_state, "altitude_m", 0.0)))
        vx = float(getattr(rocket_state, "vx_ms", 0.0))
        vy = float(getattr(rocket_state, "vy_ms", 0.0))
        vz = float(getattr(rocket_state, "vz_ms", 0.0))
        m  = float(getattr(rocket_state, "total_mass_kg",
                           getattr(rocket_state, "mass_kg", 0.0)))
        t  = float(getattr(rocket_state, "t_s", 0.0))

    # 페이로드 질량 보정
    if mission is not None and mission.payload_mass_kg > 0:
        m = mission.payload_mass_kg + mission.dry_mass_kg

    return StateVector(
        x_m=x, y_m=y, z_m=z,
        vx_ms=vx, vy_ms=vy, vz_ms=vz,
        t_s=t,
        mass_kg=m,
    )


def optional_rocket_spirit_handoff(
    rocket_state: Any,
    mission: Optional[MissionProfile] = None,
) -> Optional[StateVector]:
    """
    Rocket_Spirit NOMINAL 상태를 수신하고 StateVector로 변환.
    실패 시 None 반환 (에러 전파 없음).
    """
    try:
        sv = state_vector_from_rocket_spirit(rocket_state, mission)
        # 최소 유효성 검사: 고도가 50km 이상이어야 궤도 전파 의미 있음
        if sv.altitude_m < 50_000.0:
            return None
        return sv
    except Exception:
        return None


def build_mission_from_rocket_spirit(rocket_state: Any) -> MissionProfile:
    """
    Rocket_Spirit 상태에서 기본 MissionProfile 자동 생성.
    페이로드 질량·목표 고도를 rocket_state에서 추출하거나 기본값 사용.
    """
    try:
        alt_m  = float(getattr(rocket_state, "altitude_m",
                               getattr(rocket_state, "z_m", 400_000.0)))
        mass_kg = float(getattr(rocket_state, "total_mass_kg",
                                getattr(rocket_state, "mass_kg", 1_000.0)))
    except Exception:
        alt_m   = 400_000.0
        mass_kg = 1_000.0

    return MissionProfile(
        target_altitude_m=max(200_000.0, alt_m),
        payload_mass_kg=mass_kg,
    )
