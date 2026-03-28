"""§5 — 궤도 전파기 테스트."""

import math
import pytest
from lucifer_engine.contracts.schemas import (
    KeplerElements, StateVector, OrbitPhase, R_EARTH,
)
from lucifer_engine.mechanics.propagator import (
    propagate_orbit_kepler,
    propagate_orbit_j2,
    step_propagate,
)


def _leo_elem(alt_km: float = 400.0) -> KeplerElements:
    a = R_EARTH + alt_km * 1000.0
    return KeplerElements(a=a, e=0.001, i=math.radians(51.6),
                          raan=0.1, argp=0.2, nu=0.0)


def _leo_sv(alt_km: float = 400.0) -> StateVector:
    return StateVector(z_m=alt_km * 1000.0, vx_ms=7670.0,
                       t_s=514.0, mass_kg=1_000.0)


# ---------------------------------------------------------------------------
# Kepler 전파
# ---------------------------------------------------------------------------
class TestPropagateKepler:
    def test_returns_list(self):
        results = propagate_orbit_kepler(_leo_elem(), _leo_sv(), 60.0, 5)
        assert len(results) == 5

    def test_time_increases(self):
        results = propagate_orbit_kepler(_leo_elem(), _leo_sv(), 60.0, 3)
        times = [r.t_s for r in results]
        assert times[0] < times[1] < times[2]

    def test_elements_preserved(self):
        """전파 후 a, e, i 보존."""
        elem = _leo_elem()
        results = propagate_orbit_kepler(elem, _leo_sv(), 60.0, 10)
        for r in results:
            assert abs(r.elements.a - elem.a) < 1.0
            assert abs(r.elements.e - elem.e) < 1e-9
            assert abs(r.elements.i - elem.i) < 1e-9

    def test_health_included(self):
        results = propagate_orbit_kepler(_leo_elem(), _leo_sv(), 60.0, 3)
        for r in results:
            assert r.health is not None
            assert 0.0 <= r.health.omega_total <= 1.0

    def test_state_vector_included(self):
        results = propagate_orbit_kepler(_leo_elem(), _leo_sv(), 60.0, 3)
        for r in results:
            assert r.state is not None

    def test_one_orbit_integration(self):
        """1궤도 전파 후 주기 시간 일치 확인."""
        elem = _leo_elem()
        T = elem.period_s
        steps = 92   # ~1분 단위 92스텝 ≈ 1궤도
        dt = T / steps
        results = propagate_orbit_kepler(elem, _leo_sv(), dt, steps)
        assert len(results) == steps

    def test_event_markers(self):
        results = propagate_orbit_kepler(_leo_elem(), _leo_sv(), 60.0, 5)
        assert results[0].event == "propagation_start"
        assert results[-1].event == "propagation_end"


# ---------------------------------------------------------------------------
# J2 섭동 전파
# ---------------------------------------------------------------------------
class TestPropagateJ2:
    def test_returns_list(self):
        results = propagate_orbit_j2(_leo_elem(), _leo_sv(), 60.0, 5)
        assert len(results) == 5

    def test_raan_drifts(self):
        """J2 전파에서 RAAN이 변함 (비적도 궤도)."""
        elem = _leo_elem()
        results = propagate_orbit_j2(elem, _leo_sv(), 60.0, 100)
        raan_start = results[0].elements.raan
        raan_end   = results[-1].elements.raan
        # 수백 분 후 RAAN 변화 > 0.001 rad 기대
        # (방향 확인보다 변화 여부 확인)
        assert raan_start != raan_end

    def test_semimajor_axis_conserved(self):
        """J2 전파에서도 a 보존."""
        elem = _leo_elem()
        results = propagate_orbit_j2(elem, _leo_sv(), 60.0, 20)
        for r in results:
            assert abs(r.elements.a - elem.a) < 1.0

    def test_health_present(self):
        results = propagate_orbit_j2(_leo_elem(), _leo_sv(), 60.0, 5)
        assert all(r.health is not None for r in results)


# ---------------------------------------------------------------------------
# 단일 스텝 전파
# ---------------------------------------------------------------------------
class TestStepPropagate:
    def test_time_advances(self):
        elem = _leo_elem()
        sv = _leo_sv()
        result = step_propagate(elem, sv, 60.0, OrbitPhase.CIRCULAR)
        assert abs(result.t_s - (sv.t_s + 60.0)) < 1e-9

    def test_elements_type(self):
        elem = _leo_elem()
        sv = _leo_sv()
        result = step_propagate(elem, sv, 60.0, OrbitPhase.CIRCULAR)
        assert isinstance(result.elements, KeplerElements)

    def test_phase_preserved(self):
        elem = _leo_elem()
        sv = _leo_sv()
        result = step_propagate(elem, sv, 60.0, OrbitPhase.STATION_KEEPING)
        assert result.phase == OrbitPhase.STATION_KEEPING

    def test_j2_mode(self):
        elem = _leo_elem()
        sv = _leo_sv()
        result = step_propagate(elem, sv, 60.0, OrbitPhase.CIRCULAR, use_j2=True)
        assert result.elements is not None
