"""
Lucifer_Engine — OrbitAgent (궤도 운용 에이전트)

최상위 오케스트레이터.
입력: StateVector (Rocket_Spirit NOMINAL 출구 상태)
출력: 궤도 요소 + 건강도 + 기동 계획 + 이력 체인

FSM:
  INJECTION → (타원이면) ELLIPTICAL → CIRCULARIZING → CIRCULAR
            → (기동 필요 시) MANEUVERING → STATION_KEEPING → NOMINAL
  언제든: ABORT 가능 (근지점 대기권 진입)
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import time
from typing import List, Optional, Tuple

from lucifer_engine.contracts.schemas import (
    KeplerElements,
    ManeuverPlan,
    MissionProfile,
    OrbitHealthReport,
    OrbitPhase,
    PropagationResult,
    StateVector,
    MU_EARTH,
    R_EARTH,
)
from lucifer_engine.mechanics.maneuvers import (
    plan_plane_change,
    delta_v_budget,
)
from lucifer_engine.bridges.orbital_core_bridge import (
    state_to_elements_bridge,
    elements_to_state_bridge,
    plan_circularization_bridge,
    plan_hohmann_bridge,
    step_propagate_bridge,
)
from lucifer_engine.health.orbit_health import assess_orbit_health

# 최소 NOMINAL 조건
_MIN_OMEGA_NOMINAL = 0.80
_MIN_PERIAPSIS_ALT_M = 80_000.0    # 재진입 임계


# ---------------------------------------------------------------------------
# 궤도 이력 체인 (FlightChain 경량판)
# ---------------------------------------------------------------------------
class OrbitChain:
    """SHA-256 연결 이력 체인 (감사 추적)."""

    def __init__(self) -> None:
        self._entries: List[dict] = []

    def append(self, phase: str, data: dict) -> None:
        prev_hash = self._entries[-1]["hash"] if self._entries else "0" * 64
        entry = {
            "seq":   len(self._entries),
            "ts":    time.time(),
            "phase": phase,
            "data":  data,
        }
        blob = json.dumps(entry, sort_keys=True, default=str).encode()
        entry["hash"] = hashlib.sha256(prev_hash.encode() + blob).hexdigest()
        self._entries.append(entry)

    def phase_events(self, phase: str) -> List[dict]:
        return [e for e in self._entries if e["phase"] == phase]

    def __len__(self) -> int:
        return len(self._entries)


# ---------------------------------------------------------------------------
# OrbitAgent
# ---------------------------------------------------------------------------
class OrbitAgent:
    """
    궤도 운용 에이전트.

    Parameters
    ----------
    mission : MissionProfile — 임무 목표
    use_j2  : bool — J2 섭동 전파 사용 여부 (기본 False)
    """

    def __init__(
        self,
        mission: Optional[MissionProfile] = None,
        use_j2: bool = False,
    ) -> None:
        self._mission = mission or MissionProfile()
        self._use_j2  = use_j2

        self._phase:   OrbitPhase = OrbitPhase.INJECTION
        self._elem:    Optional[KeplerElements] = None
        self._sv:      Optional[StateVector]    = None
        self._health:  Optional[OrbitHealthReport] = None
        self._plan:    Optional[ManeuverPlan]   = None

        self.chain = OrbitChain()
        self._t_s:  float = 0.0

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------

    @property
    def phase(self) -> OrbitPhase:
        return self._phase

    @property
    def elements(self) -> Optional[KeplerElements]:
        return self._elem

    @property
    def health(self) -> Optional[OrbitHealthReport]:
        return self._health

    @property
    def maneuver_plan(self) -> Optional[ManeuverPlan]:
        return self._plan

    def inject(self, sv: StateVector) -> OrbitHealthReport:
        """
        Rocket_Spirit NOMINAL 상태 수신 — 궤도 요소 계산 및 초기 건강도 판정.
        """
        self._sv   = sv
        self._t_s  = sv.t_s
        self._elem = state_to_elements_bridge(sv)
        self._health = assess_orbit_health(
            self._elem,
            phase=OrbitPhase.INJECTION,
            target_inclination_rad=math.radians(self._mission.target_inclination_deg),
            target_altitude_m=self._mission.target_altitude_m,
        )

        # 단계 판정
        if self._health.blockers:
            self._phase = OrbitPhase.ABORT
        elif self._elem.is_escape:
            self._phase = OrbitPhase.ABORT
        elif self._elem.is_circular:
            self._phase = OrbitPhase.CIRCULAR
        else:
            self._phase = OrbitPhase.ELLIPTICAL

        self.chain.append("injection", {
            "phase":       self._phase.value,
            "altitude_km": round(sv.altitude_m / 1000.0, 2),
            "speed_ms":    round(sv.speed_ms, 1),
            "a_km":        round(self._elem.a / 1000.0, 2),
            "e":           round(self._elem.e, 5),
            "i_deg":       round(self._elem.inclination_deg, 2),
            "omega_total": self._health.omega_total,
            "verdict":     self._health.verdict,
        })

        return self._health

    def plan_maneuvers(self) -> ManeuverPlan:
        """
        현재 궤도 상태에 맞는 기동 계획 수립.
        ELLIPTICAL → 원형화 번
        고도 불일치 → 호만 전이
        경사각 불일치 → 궤도면 변경
        """
        if self._elem is None:
            return ManeuverPlan()

        steps: List = []
        total_dv = 0.0

        # 1. 원형화 필요?
        if not self._elem.is_circular and not self._elem.is_escape:
            circ_plan = plan_circularization_bridge(self._elem, self._mission)
            steps.extend(circ_plan.steps)
            total_dv += circ_plan.total_delta_v_ms

        # 2. 고도 조정 필요?
        target_r = R_EARTH + self._mission.target_altitude_m
        current_r = self._elem.apoapsis_m
        alt_diff = abs(current_r - target_r)
        if alt_diff > 20_000.0:   # 20km 이상 차이 시 호만
            hoh_plan = plan_hohmann_bridge(current_r, target_r, self._mission)
            steps.extend(hoh_plan.steps)
            total_dv += hoh_plan.total_delta_v_ms

        # 3. 경사각 조정 필요?
        target_inc = math.radians(self._mission.target_inclination_deg)
        di = abs(self._elem.i - target_inc)
        if di > math.radians(2.0):   # 2° 이상 차이 시 면 변경
            plane_plan = plan_plane_change(self._elem, target_inc, self._mission)
            steps.extend(plane_plan.steps)
            total_dv += plane_plan.total_delta_v_ms

        self._plan = ManeuverPlan(
            steps=tuple(steps),
            total_delta_v_ms=total_dv,
            target_altitude_m=self._mission.target_altitude_m,
            target_inclination_rad=target_inc,
        )

        budget = delta_v_budget(self._mission, self._plan)
        self.chain.append("maneuver_plan", {
            "n_burns":       self._plan.n_burns,
            "total_dv_ms":   round(total_dv, 1),
            "budget_ok":     budget["budget_ok"],
            "remaining_ms":  round(budget["remaining_ms"], 1),
        })

        return self._plan

    def execute_circularization(self) -> OrbitHealthReport:
        """
        원형화 번 실행 — 원지점에서 원 궤도로 즉시 전환 (순간 ΔV 모델).
        """
        if self._elem is None:
            raise RuntimeError("inject() 먼저 호출 필요")

        # 원지점 고도의 원 궤도로 요소 업데이트
        ra = self._elem.apoapsis_m
        # 원 궤도 a = ra, e = 0
        new_elem = dataclasses.replace(self._elem, a=ra, e=0.0, nu=0.0)
        self._elem  = new_elem
        self._phase = OrbitPhase.CIRCULAR

        self._health = assess_orbit_health(
            self._elem,
            phase=OrbitPhase.CIRCULAR,
            target_inclination_rad=math.radians(self._mission.target_inclination_deg),
            target_altitude_m=self._mission.target_altitude_m,
        )

        sv_new = elements_to_state_bridge(
            new_elem,
            t_s=self._t_s,
            mass_kg=self._sv.mass_kg if self._sv else 0.0,
        )
        self._sv = sv_new

        self.chain.append("circularization", {
            "a_km":        round(ra / 1000.0, 2),
            "e_after":     0.0,
            "alt_km":      round((ra - R_EARTH) / 1000.0, 2),
            "omega_total": self._health.omega_total,
            "verdict":     self._health.verdict,
        })

        return self._health

    def tick(self, dt_s: float = 60.0) -> PropagationResult:
        """
        dt_s 초 궤도 전파 (에이전트 루프 단위 틱).
        """
        if self._elem is None or self._sv is None:
            raise RuntimeError("inject() 먼저 호출 필요")

        result = step_propagate_bridge(
            self._elem, self._sv, dt_s,
            phase=self._phase,
            use_j2=self._use_j2,
        )

        self._elem   = result.elements
        self._sv     = result.state
        self._health = result.health
        self._t_s    = result.t_s

        # 근지점 ABORT 감시
        if self._elem.periapsis_altitude_m < _MIN_PERIAPSIS_ALT_M:
            self._phase = OrbitPhase.ABORT
            self.chain.append("abort", {
                "reason": "periapsis_below_atmosphere",
                "peri_alt_km": round(self._elem.periapsis_altitude_m / 1000.0, 2),
            })

        return result

    def run_to_nominal(
        self,
        max_steps: int = 200,
        dt_s: float = 60.0,
    ) -> Tuple[bool, List[PropagationResult]]:
        """
        NOMINAL 도달까지 자동 루프.

        1. inject 이후 호출
        2. 타원 궤도 → 원형화 자동 실행
        3. 원 궤도 → NOMINAL 판정

        Returns
        -------
        (success, results_list)
        """
        results: List[PropagationResult] = []

        if self._phase == OrbitPhase.ABORT:
            return False, results

        # 타원이면 원형화 먼저
        if self._phase == OrbitPhase.ELLIPTICAL:
            self.execute_circularization()

        # 전파 루프
        for _ in range(max_steps):
            res = self.tick(dt_s)
            results.append(res)

            if self._phase == OrbitPhase.ABORT:
                return False, results

            # NOMINAL 조건: Ω_total ≥ 0.80, 원 궤도, 근지점 안전
            if (
                self._health.omega_total >= _MIN_OMEGA_NOMINAL
                and self._elem.is_circular
                and self._elem.periapsis_altitude_m >= 150_000.0
            ):
                self._phase = OrbitPhase.NOMINAL
                self.chain.append("nominal", {
                    "t_s":       round(self._t_s, 1),
                    "alt_km":    round(self._elem.periapsis_altitude_m / 1000.0, 2),
                    "period_min": round(self._elem.period_s / 60.0, 1),
                    "omega_total": self._health.omega_total,
                })
                return True, results

        return False, results

    def summary(self) -> str:
        """현재 궤도 상태 요약 텍스트."""
        if self._elem is None:
            return "OrbitAgent: 초기화 전 (inject() 필요)"

        h = self._health
        e = self._elem
        lines = [
            f"Lucifer_Engine — OrbitAgent",
            f"  단계:       {self._phase.value}",
            f"  고도(근지점): {e.periapsis_altitude_m/1000:.1f} km",
            f"  고도(원지점): {e.apoapsis_altitude_m/1000:.1f} km",
            f"  이심률:     {e.e:.5f}",
            f"  경사각:     {e.inclination_deg:.2f}°",
            f"  주기:       {e.period_s/60:.1f} min",
            f"  Ω_total:    {h.omega_total:.4f}  [{h.verdict}]",
            f"    Ω_peri={h.omega_periapsis:.3f}  Ω_enrg={h.omega_energy:.3f}  "
            f"Ω_ecc={h.omega_eccentricity:.3f}  Ω_inc={h.omega_inclination:.3f}  "
            f"Ω_cov={h.omega_coverage:.3f}",
        ]
        if h.blockers:
            lines.append(f"  BLOCKERS: {', '.join(h.blockers)}")
        if self._plan:
            lines.append(
                f"  기동계획:   {self._plan.n_burns}번 번, "
                f"총 ΔV={self._plan.total_delta_v_ms:.1f} m/s"
            )
        return "\n".join(lines)
