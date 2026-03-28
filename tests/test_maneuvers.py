"""§3 — 궤도 기동 계획 테스트."""

import math
import pytest
from lucifer_engine.contracts.schemas import (
    KeplerElements, MissionProfile, ManeuverType, R_EARTH,
)
from lucifer_engine.mechanics.maneuvers import (
    plan_circularization,
    plan_hohmann,
    plan_plane_change,
    plan_deorbit,
    delta_v_budget,
)


def _leo_elliptic_elem(rp_alt: float = 200_000.0, ra_alt: float = 400_000.0) -> KeplerElements:
    rp = R_EARTH + rp_alt
    ra = R_EARTH + ra_alt
    a  = 0.5 * (rp + ra)
    e  = (ra - rp) / (ra + rp)
    return KeplerElements(a=a, e=e, i=math.radians(28.5),
                          raan=0.0, argp=0.0, nu=0.0)


def _leo_circular_elem(alt: float = 400_000.0) -> KeplerElements:
    a = R_EARTH + alt
    return KeplerElements(a=a, e=0.001, i=math.radians(28.5),
                          raan=0.0, argp=0.0, nu=0.0)


def _default_mission() -> MissionProfile:
    return MissionProfile(
        target_altitude_m=400_000.0,
        payload_mass_kg=1_000.0,
        dry_mass_kg=500.0,
        max_delta_v_ms=2_000.0,
        isp_s=320.0,
    )


# ---------------------------------------------------------------------------
# 원형화 번
# ---------------------------------------------------------------------------
class TestCircularization:
    def test_delta_v_positive(self):
        elem = _leo_elliptic_elem()
        plan = plan_circularization(elem, _default_mission())
        assert plan.total_delta_v_ms > 0.0

    def test_single_step(self):
        elem = _leo_elliptic_elem()
        plan = plan_circularization(elem, _default_mission())
        assert plan.n_burns == 1

    def test_burn_type(self):
        elem = _leo_elliptic_elem()
        plan = plan_circularization(elem, _default_mission())
        assert plan.steps[0].maneuver_type == ManeuverType.CIRCULARIZE

    def test_executed_at_apoapsis(self):
        """원형화 번은 원지점(ν=π)에서 실행."""
        elem = _leo_elliptic_elem()
        plan = plan_circularization(elem, _default_mission())
        assert abs(plan.steps[0].true_anomaly_rad - math.pi) < 1e-9

    def test_dv_small_for_nearly_circular(self):
        """거의 원 궤도라면 ΔV 작음."""
        elem = _leo_elliptic_elem(rp_alt=398_000.0, ra_alt=402_000.0)
        plan = plan_circularization(elem, _default_mission())
        assert plan.total_delta_v_ms < 20.0  # 20 m/s 미만

    def test_burn_duration_positive(self):
        elem = _leo_elliptic_elem()
        plan = plan_circularization(elem, _default_mission())
        assert plan.steps[0].burn_duration_s > 0.0


# ---------------------------------------------------------------------------
# 호만 전이
# ---------------------------------------------------------------------------
class TestHohmann:
    def test_two_burns(self):
        r1 = R_EARTH + 300_000.0
        r2 = R_EARTH + 600_000.0
        plan = plan_hohmann(r1, r2, _default_mission())
        assert plan.n_burns == 2

    def test_delta_v_positive(self):
        r1 = R_EARTH + 300_000.0
        r2 = R_EARTH + 600_000.0
        plan = plan_hohmann(r1, r2, _default_mission())
        assert plan.total_delta_v_ms > 0.0

    def test_upward_transfer(self):
        """낮은 궤도 → 높은 궤도: 두 번의 가속."""
        r1 = R_EARTH + 200_000.0
        r2 = R_EARTH + 800_000.0
        plan = plan_hohmann(r1, r2, _default_mission())
        assert plan.steps[0].delta_v_ms > 0.0
        assert plan.steps[1].delta_v_ms > 0.0

    def test_same_orbit_small_dv(self):
        """같은 고도 전이: ΔV ≈ 0."""
        r = R_EARTH + 400_000.0
        plan = plan_hohmann(r, r, _default_mission())
        assert plan.total_delta_v_ms < 1.0

    def test_target_altitude(self):
        r1 = R_EARTH + 300_000.0
        r2 = R_EARTH + 600_000.0
        plan = plan_hohmann(r1, r2, _default_mission())
        assert abs(plan.target_altitude_m - 600_000.0) < 1.0

    def test_leo_to_geo_dv(self):
        """LEO → GEO 호만 전이 ΔV ≈ 3.9 km/s."""
        r1 = R_EARTH + 400_000.0
        r2 = R_EARTH + 35_786_000.0
        plan = plan_hohmann(r1, r2, _default_mission())
        # 총 ΔV 3.5~4.5 km/s 범위
        assert 3_500 < plan.total_delta_v_ms < 4_500


# ---------------------------------------------------------------------------
# 궤도면 변경
# ---------------------------------------------------------------------------
class TestPlaneChange:
    def test_no_change_needed(self):
        elem = _leo_circular_elem()
        plan = plan_plane_change(elem, elem.i, _default_mission())
        assert plan.n_burns == 0

    def test_small_change(self):
        elem = _leo_circular_elem()
        new_i = elem.i + math.radians(5.0)
        plan = plan_plane_change(elem, new_i, _default_mission())
        assert plan.n_burns == 1
        assert plan.total_delta_v_ms > 0.0

    def test_dv_proportional_to_angle(self):
        """각도가 클수록 ΔV 증가."""
        elem = _leo_circular_elem()
        plan5  = plan_plane_change(elem, elem.i + math.radians(5.0),  _default_mission())
        plan10 = plan_plane_change(elem, elem.i + math.radians(10.0), _default_mission())
        assert plan10.total_delta_v_ms > plan5.total_delta_v_ms

    def test_90_deg_change(self):
        """90° 변경: ΔV = sqrt(2)·v_c."""
        elem = _leo_circular_elem()
        plan = plan_plane_change(elem, elem.i + math.radians(90.0), _default_mission())
        v_c = elem.circular_velocity_ms
        expected = math.sqrt(2.0) * v_c
        assert abs(plan.total_delta_v_ms - expected) / expected < 0.02


# ---------------------------------------------------------------------------
# 재진입 번
# ---------------------------------------------------------------------------
class TestDeorbit:
    def test_single_step(self):
        elem = _leo_circular_elem()
        plan = plan_deorbit(elem, 50_000.0, _default_mission())
        assert plan.n_burns == 1

    def test_deorbit_dv_positive(self):
        elem = _leo_circular_elem()
        plan = plan_deorbit(elem, 50_000.0, _default_mission())
        assert plan.total_delta_v_ms > 0.0

    def test_maneuver_type(self):
        elem = _leo_circular_elem()
        plan = plan_deorbit(elem, 50_000.0, _default_mission())
        assert plan.steps[0].maneuver_type == ManeuverType.DEORBIT


# ---------------------------------------------------------------------------
# ΔV 예산
# ---------------------------------------------------------------------------
class TestDeltaVBudget:
    def test_within_budget(self):
        mission = _default_mission()  # max=2000
        elem = _leo_elliptic_elem()
        plan = plan_circularization(elem, mission)
        budget = delta_v_budget(mission, plan)
        assert budget["available_ms"] == 2_000.0
        assert budget["used_ms"] == plan.total_delta_v_ms

    def test_budget_ok_flag(self):
        mission = MissionProfile(max_delta_v_ms=10_000.0)
        elem = _leo_elliptic_elem()
        plan = plan_circularization(elem, mission)
        budget = delta_v_budget(mission, plan)
        assert budget["budget_ok"] is True

    def test_budget_exceeded(self):
        mission = MissionProfile(max_delta_v_ms=1.0)  # 극단적으로 작은 예산
        r1 = R_EARTH + 300_000.0
        r2 = R_EARTH + 600_000.0
        plan = plan_hohmann(r1, r2, mission)
        budget = delta_v_budget(mission, plan)
        assert budget["budget_ok"] is False
