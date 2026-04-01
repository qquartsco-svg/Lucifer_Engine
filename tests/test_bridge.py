"""§6 — Rocket_Spirit 브리지 테스트."""

import math
import pytest
from lucifer_engine.contracts.schemas import MissionProfile, R_EARTH
from lucifer_engine.bridges.rocket_spirit_bridge import (
    state_vector_from_rocket_spirit,
    optional_rocket_spirit_handoff,
    build_mission_from_rocket_spirit,
)
from lucifer_engine.bridges.orbital_core_bridge import (
    orbital_core_available,
    state_to_elements_bridge,
    elements_to_state_bridge,
    plan_hohmann_bridge,
    plan_circularization_bridge,
    step_propagate_bridge,
)
from lucifer_engine.contracts.schemas import KeplerElements, OrbitPhase, StateVector


# ---------------------------------------------------------------------------
# 딕셔너리 입력
# ---------------------------------------------------------------------------
class TestBridgeDict:
    def _nominal_dict(self) -> dict:
        return {
            "x_m":  0.0,
            "y_m":  0.0,
            "z_m":  444_000.0,
            "vx_ms": 7_600.0,
            "vy_ms": 200.0,
            "vz_ms": 50.0,
            "total_mass_kg": 1_500.0,
            "t_s": 514.0,
        }

    def test_altitude(self):
        sv = state_vector_from_rocket_spirit(self._nominal_dict())
        assert abs(sv.altitude_m - 444_000.0) < 1.0

    def test_speed(self):
        sv = state_vector_from_rocket_spirit(self._nominal_dict())
        assert sv.speed_ms > 7_000.0

    def test_mass(self):
        sv = state_vector_from_rocket_spirit(self._nominal_dict())
        assert sv.mass_kg == 1_500.0

    def test_time(self):
        sv = state_vector_from_rocket_spirit(self._nominal_dict())
        assert abs(sv.t_s - 514.0) < 1e-9

    def test_mission_override(self):
        """mission 주어지면 mass를 미션 기준으로 보정."""
        mission = MissionProfile(payload_mass_kg=800.0, dry_mass_kg=200.0)
        sv = state_vector_from_rocket_spirit(self._nominal_dict(), mission)
        assert sv.mass_kg == 1_000.0  # 800 + 200


# ---------------------------------------------------------------------------
# duck-type 객체 입력 (RocketState 시뮬)
# ---------------------------------------------------------------------------
class _FakeRocketState:
    def __init__(self):
        self.x_m = 0.0
        self.y_m = 0.0
        self.z_m = 444_000.0
        self.vx_ms = 7_600.0
        self.vy_ms = 200.0
        self.vz_ms = 50.0
        self.total_mass_kg = 1_200.0
        self.t_s = 514.0


class TestBridgeDuckType:
    def test_altitude(self):
        sv = state_vector_from_rocket_spirit(_FakeRocketState())
        assert abs(sv.altitude_m - 444_000.0) < 1.0

    def test_mass(self):
        sv = state_vector_from_rocket_spirit(_FakeRocketState())
        assert sv.mass_kg == 1_200.0


# ---------------------------------------------------------------------------
# tuple 입력
# ---------------------------------------------------------------------------
class TestBridgeTuple:
    def test_tuple_input(self):
        data = (0.0, 0.0, 444_000.0, 7_600.0, 200.0, 50.0, 1_000.0, 514.0)
        sv = state_vector_from_rocket_spirit(data)
        assert abs(sv.altitude_m - 444_000.0) < 1.0
        assert abs(sv.t_s - 514.0) < 1e-9


# ---------------------------------------------------------------------------
# optional_rocket_spirit_handoff
# ---------------------------------------------------------------------------
class TestOptionalHandoff:
    def test_valid_state_returns_sv(self):
        state = _FakeRocketState()
        sv = optional_rocket_spirit_handoff(state)
        assert sv is not None
        assert sv.altitude_m > 50_000.0

    def test_low_altitude_returns_none(self):
        """50km 미만 → None 반환."""
        state = _FakeRocketState()
        state.z_m = 30_000.0
        sv = optional_rocket_spirit_handoff(state)
        assert sv is None

    def test_invalid_input_returns_none(self):
        """예외 발생 시 None 반환."""
        sv = optional_rocket_spirit_handoff(None)
        # None 입력 → AttributeError 발생 → None 반환
        assert sv is None


# ---------------------------------------------------------------------------
# build_mission_from_rocket_spirit
# ---------------------------------------------------------------------------
class TestBuildMission:
    def test_altitude_from_state(self):
        state = _FakeRocketState()
        mission = build_mission_from_rocket_spirit(state)
        # z_m=444km → target_altitude ≥ 200km
        assert mission.target_altitude_m >= 200_000.0

    def test_mass_from_state(self):
        state = _FakeRocketState()
        mission = build_mission_from_rocket_spirit(state)
        assert mission.payload_mass_kg == state.total_mass_kg

    def test_fallback_on_error(self):
        """오류 시 기본값 사용."""
        mission = build_mission_from_rocket_spirit(object())
        assert mission.target_altitude_m >= 200_000.0


class TestOrbitalCoreBridge:
    def test_bridge_availability_is_bool(self):
        assert isinstance(orbital_core_available(), bool)

    def test_hohmann_bridge_returns_plan(self):
        mission = MissionProfile(target_altitude_m=444_000.0)
        plan = plan_hohmann_bridge(R_EARTH + 400_000.0, R_EARTH + 500_000.0, mission)
        assert plan.total_delta_v_ms >= 0.0
        assert len(plan.steps) >= 1

    def test_circularization_bridge_returns_plan(self):
        mission = MissionProfile(target_altitude_m=444_000.0)
        elem = KeplerElements(
            a=R_EARTH + 444_000.0,
            e=0.05,
            i=math.radians(28.5),
            raan=0.0,
            argp=0.0,
            nu=0.0,
        )
        plan = plan_circularization_bridge(elem, mission)
        assert plan.total_delta_v_ms >= 0.0
        assert len(plan.steps) >= 1

    def test_step_propagate_bridge_returns_result(self):
        elem = KeplerElements(
            a=R_EARTH + 444_000.0,
            e=0.01,
            i=math.radians(28.5),
            raan=0.0,
            argp=0.0,
            nu=0.0,
        )
        sv = StateVector(
            x_m=R_EARTH + 444_000.0,
            y_m=0.0,
            z_m=444_000.0,
            vx_ms=0.0,
            vy_ms=7_650.0,
            vz_ms=0.0,
            t_s=0.0,
            mass_kg=1000.0,
        )
        result = step_propagate_bridge(elem, sv, 60.0, OrbitPhase.CIRCULAR, use_j2=True)
        assert result.t_s >= 60.0
        assert result.state.mass_kg == 1000.0
        assert result.elements.a > 0.0

    def test_state_to_elements_bridge_returns_elements(self):
        sv = StateVector(
            x_m=R_EARTH + 444_000.0,
            y_m=0.0,
            z_m=444_000.0,
            vx_ms=0.0,
            vy_ms=7_650.0,
            vz_ms=0.0,
            t_s=0.0,
            mass_kg=1000.0,
        )
        elem = state_to_elements_bridge(sv)
        assert elem.a > 0.0
        assert elem.e >= 0.0

    def test_elements_to_state_bridge_returns_state(self):
        elem = KeplerElements(
            a=R_EARTH + 444_000.0,
            e=0.01,
            i=math.radians(28.5),
            raan=0.0,
            argp=0.0,
            nu=0.0,
        )
        sv = elements_to_state_bridge(elem, t_s=10.0, mass_kg=900.0)
        assert sv.t_s == 10.0
        assert sv.mass_kg == 900.0
        assert sv.altitude_m > 0.0
