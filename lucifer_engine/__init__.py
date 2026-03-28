"""
Lucifer_Engine — 궤도 전파 엔진

Rocket_Spirit 발사체가 MECO·궤도삽입 후 인계하는 궤도 역학 레이어.

주요 수출:
  StateVector              — 위치·속도 계약
  KeplerElements           — 케플러 6요소
  OrbitPhase               — 궤도 단계 FSM
  OrbitHealthReport        — Ω 건강도 판정
  MissionProfile           — 임무 프로파일
  ManeuverPlan             — 기동 계획
  OrbitAgent               — 최상위 오케스트레이터
  state_to_elements        — 상태 벡터 → 케플러 요소
  elements_to_state        — 케플러 요소 → 상태 벡터
  assess_orbit_health      — Ω 건강도 평가
  state_vector_from_rocket_spirit  — Rocket_Spirit 브리지
"""

__version__ = "0.1.0"

from lucifer_engine.contracts.schemas import (
    StateVector,
    KeplerElements,
    OrbitPhase,
    OrbitHealthReport,
    ManeuverPlan,
    ManeuverStep,
    ManeuverType,
    MissionProfile,
    PropagationResult,
    MU_EARTH,
    R_EARTH,
    J2,
)
from lucifer_engine.mechanics.kepler import (
    state_to_elements,
    elements_to_state,
    propagate_kepler,
    circular_velocity_ms,
    orbital_period_s,
    escape_velocity_ms,
    vis_viva_ms,
)
from lucifer_engine.mechanics.maneuvers import (
    plan_circularization,
    plan_hohmann,
    plan_plane_change,
    plan_deorbit,
    delta_v_budget,
)
from lucifer_engine.mechanics.propagator import (
    propagate_orbit_kepler,
    propagate_orbit_j2,
    step_propagate,
)
from lucifer_engine.health.orbit_health import assess_orbit_health
from lucifer_engine.bridges.rocket_spirit_bridge import (
    state_vector_from_rocket_spirit,
    optional_rocket_spirit_handoff,
    build_mission_from_rocket_spirit,
)
from lucifer_engine.agent.orbit_agent import OrbitAgent, OrbitChain

__all__ = [
    # 계약
    "StateVector", "KeplerElements", "OrbitPhase", "OrbitHealthReport",
    "ManeuverPlan", "ManeuverStep", "ManeuverType", "MissionProfile",
    "PropagationResult", "MU_EARTH", "R_EARTH", "J2",
    # 역학
    "state_to_elements", "elements_to_state", "propagate_kepler",
    "circular_velocity_ms", "orbital_period_s", "escape_velocity_ms", "vis_viva_ms",
    # 기동
    "plan_circularization", "plan_hohmann", "plan_plane_change",
    "plan_deorbit", "delta_v_budget",
    # 전파
    "propagate_orbit_kepler", "propagate_orbit_j2", "step_propagate",
    # 건강도
    "assess_orbit_health",
    # 브리지
    "state_vector_from_rocket_spirit", "optional_rocket_spirit_handoff",
    "build_mission_from_rocket_spirit",
    # 에이전트
    "OrbitAgent", "OrbitChain",
]
