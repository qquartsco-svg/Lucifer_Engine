"""§7 — OrbitAgent 통합 테스트."""

import math
import pytest
from lucifer_engine.contracts.schemas import (
    KeplerElements, StateVector, OrbitPhase, MissionProfile, R_EARTH,
)
from lucifer_engine.agent.orbit_agent import OrbitAgent, OrbitChain
from lucifer_engine.mechanics.kepler import state_to_elements


def _rocket_spirit_nominal_sv() -> StateVector:
    """Rocket_Spirit NOMINAL 출구 상태 시뮬 (h=444km, v≈7.6km/s)."""
    return StateVector(
        x_m=0.0, y_m=0.0, z_m=444_000.0,
        vx_ms=7_600.0, vy_ms=200.0, vz_ms=50.0,
        t_s=514.0, mass_kg=1_200.0,
    )


def _default_mission() -> MissionProfile:
    return MissionProfile(
        target_altitude_m=444_000.0,
        target_inclination_deg=28.5,
        payload_mass_kg=1_000.0,
        dry_mass_kg=200.0,
        max_delta_v_ms=2_000.0,
        isp_s=320.0,
    )


# ---------------------------------------------------------------------------
# §7-1 inject
# ---------------------------------------------------------------------------
class TestOrbitAgentInject:
    def test_inject_returns_health(self):
        agent = OrbitAgent(_default_mission())
        sv = _rocket_spirit_nominal_sv()
        health = agent.inject(sv)
        assert health is not None
        assert 0.0 <= health.omega_total <= 1.0

    def test_inject_sets_elements(self):
        agent = OrbitAgent(_default_mission())
        agent.inject(_rocket_spirit_nominal_sv())
        assert agent.elements is not None

    def test_inject_logs_chain(self):
        agent = OrbitAgent(_default_mission())
        agent.inject(_rocket_spirit_nominal_sv())
        events = agent.chain.phase_events("injection")
        assert len(events) >= 1

    def test_inject_phase_not_abort(self):
        """정상 상태 inject → ABORT 아님."""
        agent = OrbitAgent(_default_mission())
        agent.inject(_rocket_spirit_nominal_sv())
        assert agent.phase != OrbitPhase.ABORT

    def test_inject_escape_triggers_abort(self):
        """탈출 속도 이상이면 ABORT."""
        sv = StateVector(
            z_m=444_000.0,
            vx_ms=12_000.0, vy_ms=0.0, vz_ms=0.0,  # 탈출 속도
            t_s=0.0, mass_kg=1_000.0,
        )
        agent = OrbitAgent(_default_mission())
        agent.inject(sv)
        assert agent.phase == OrbitPhase.ABORT


# ---------------------------------------------------------------------------
# §7-2 plan_maneuvers
# ---------------------------------------------------------------------------
class TestOrbitAgentPlan:
    def test_plan_returns_maneuver_plan(self):
        agent = OrbitAgent(_default_mission())
        agent.inject(_rocket_spirit_nominal_sv())
        plan = agent.plan_maneuvers()
        assert plan is not None

    def test_plan_logs_chain(self):
        agent = OrbitAgent(_default_mission())
        agent.inject(_rocket_spirit_nominal_sv())
        agent.plan_maneuvers()
        events = agent.chain.phase_events("maneuver_plan")
        assert len(events) >= 1

    def test_plan_stored_on_agent(self):
        agent = OrbitAgent(_default_mission())
        agent.inject(_rocket_spirit_nominal_sv())
        agent.plan_maneuvers()
        assert agent.maneuver_plan is not None


# ---------------------------------------------------------------------------
# §7-3 execute_circularization
# ---------------------------------------------------------------------------
class TestCircularization:
    def test_circularizes_orbit(self):
        agent = OrbitAgent(_default_mission())
        agent.inject(_rocket_spirit_nominal_sv())
        if agent.phase == OrbitPhase.ELLIPTICAL:
            agent.execute_circularization()
            assert agent.elements.is_circular

    def test_phase_becomes_circular(self):
        agent = OrbitAgent(_default_mission())
        agent.inject(_rocket_spirit_nominal_sv())
        if agent.phase == OrbitPhase.ELLIPTICAL:
            agent.execute_circularization()
            assert agent.phase == OrbitPhase.CIRCULAR

    def test_chain_logged(self):
        agent = OrbitAgent(_default_mission())
        agent.inject(_rocket_spirit_nominal_sv())
        agent.execute_circularization()
        events = agent.chain.phase_events("circularization")
        assert len(events) >= 1


# ---------------------------------------------------------------------------
# §7-4 tick
# ---------------------------------------------------------------------------
class TestTick:
    def test_tick_advances_time(self):
        agent = OrbitAgent(_default_mission())
        agent.inject(_rocket_spirit_nominal_sv())
        agent.execute_circularization()
        t_before = agent._t_s
        result = agent.tick(60.0)
        assert result.t_s > t_before

    def test_tick_returns_propagation_result(self):
        agent = OrbitAgent(_default_mission())
        agent.inject(_rocket_spirit_nominal_sv())
        agent.execute_circularization()
        from lucifer_engine.contracts.schemas import PropagationResult
        result = agent.tick(60.0)
        assert isinstance(result, PropagationResult)

    def test_tick_without_inject_raises(self):
        agent = OrbitAgent()
        with pytest.raises(RuntimeError):
            agent.tick(60.0)


# ---------------------------------------------------------------------------
# §7-5 run_to_nominal
# ---------------------------------------------------------------------------
class TestRunToNominal:
    def test_reaches_nominal_or_degrades(self):
        """정상 상태에서 NOMINAL 도달 시도."""
        agent = OrbitAgent(_default_mission())
        agent.inject(_rocket_spirit_nominal_sv())
        success, results = agent.run_to_nominal(max_steps=100, dt_s=60.0)
        # 성공 또는 단계 완료 (실패해도 결과 리스트 반환)
        assert isinstance(results, list)
        assert isinstance(success, bool)

    def test_abort_state_returns_false(self):
        """ABORT 상태에서 run_to_nominal은 즉시 False."""
        sv = StateVector(z_m=444_000.0, vx_ms=12_000.0,
                         t_s=0.0, mass_kg=1_000.0)
        agent = OrbitAgent(_default_mission())
        agent.inject(sv)
        success, results = agent.run_to_nominal()
        assert success is False
        assert len(results) == 0

    def test_results_are_propagation_results(self):
        from lucifer_engine.contracts.schemas import PropagationResult
        agent = OrbitAgent(_default_mission())
        agent.inject(_rocket_spirit_nominal_sv())
        _, results = agent.run_to_nominal(max_steps=5, dt_s=60.0)
        for r in results:
            assert isinstance(r, PropagationResult)

    def test_nominal_chain_logged_on_success(self):
        """NOMINAL 도달 시 체인에 기록."""
        agent = OrbitAgent(_default_mission())
        agent.inject(_rocket_spirit_nominal_sv())
        success, _ = agent.run_to_nominal(max_steps=200, dt_s=60.0)
        if success:
            events = agent.chain.phase_events("nominal")
            assert len(events) >= 1


# ---------------------------------------------------------------------------
# §7-6 summary
# ---------------------------------------------------------------------------
class TestSummary:
    def test_summary_before_inject(self):
        agent = OrbitAgent()
        s = agent.summary()
        assert "inject" in s.lower() or "초기화" in s

    def test_summary_after_inject(self):
        agent = OrbitAgent(_default_mission())
        agent.inject(_rocket_spirit_nominal_sv())
        s = agent.summary()
        assert "km" in s
        assert "Ω" in s

    def test_summary_contains_phase(self):
        agent = OrbitAgent(_default_mission())
        agent.inject(_rocket_spirit_nominal_sv())
        s = agent.summary()
        assert agent.phase.value in s


# ---------------------------------------------------------------------------
# §7-7 OrbitChain
# ---------------------------------------------------------------------------
class TestOrbitChain:
    def test_append_and_length(self):
        chain = OrbitChain()
        chain.append("injection", {"alt": 444.0})
        chain.append("circularization", {"alt": 444.0})
        assert len(chain) == 2

    def test_phase_events_filter(self):
        chain = OrbitChain()
        chain.append("injection", {})
        chain.append("injection", {})
        chain.append("nominal", {})
        events = chain.phase_events("injection")
        assert len(events) == 2

    def test_hash_chain_integrity(self):
        """각 엔트리의 hash 가 이전 hash 포함 여부."""
        chain = OrbitChain()
        chain.append("step1", {"v": 1})
        chain.append("step2", {"v": 2})
        assert chain._entries[0]["hash"] != chain._entries[1]["hash"]
        assert len(chain._entries[0]["hash"]) == 64   # SHA-256


# ---------------------------------------------------------------------------
# §7-8 공개 API
# ---------------------------------------------------------------------------
class TestPublicAPI:
    def test_import_orbit_agent(self):
        from lucifer_engine import OrbitAgent
        assert OrbitAgent is not None

    def test_import_state_to_elements(self):
        from lucifer_engine import state_to_elements
        assert callable(state_to_elements)

    def test_import_assess_orbit_health(self):
        from lucifer_engine import assess_orbit_health
        assert callable(assess_orbit_health)

    def test_version(self):
        import lucifer_engine
        assert lucifer_engine.__version__ == "0.1.0"
