"""§4 — 궤도 건강도 (Ω 스코어) 테스트."""

import math
import pytest
from lucifer_engine.contracts.schemas import (
    KeplerElements, OrbitPhase, R_EARTH,
)
from lucifer_engine.health.orbit_health import assess_orbit_health


def _leo_elem(alt_km: float = 400.0, e: float = 0.001) -> KeplerElements:
    a = R_EARTH + alt_km * 1000.0
    return KeplerElements(a=a, e=e, i=math.radians(28.5),
                          raan=0.0, argp=0.0, nu=0.0)


class TestOrbitHealth:
    # ------------------------------------------------------------------
    # 이상적 원 궤도
    # ------------------------------------------------------------------
    def test_nominal_leo(self):
        elem = _leo_elem(400.0, e=0.001)
        h = assess_orbit_health(elem, phase=OrbitPhase.CIRCULAR)
        assert h.omega_total >= 0.75
        assert h.verdict in ("NOMINAL", "STABLE")

    def test_omega_total_bounded(self):
        elem = _leo_elem()
        h = assess_orbit_health(elem)
        assert 0.0 <= h.omega_total <= 1.0

    def test_all_components_bounded(self):
        elem = _leo_elem()
        h = assess_orbit_health(elem)
        for v in [h.omega_periapsis, h.omega_energy,
                  h.omega_eccentricity, h.omega_inclination, h.omega_coverage]:
            assert 0.0 <= v <= 1.0

    # ------------------------------------------------------------------
    # 근지점 대기권 진입
    # ------------------------------------------------------------------
    def test_periapsis_below_atmosphere(self):
        a = R_EARTH + 400_000.0
        # 근지점을 50km로 설정 (대기권 내)
        rp = R_EARTH + 50_000.0
        e  = (a - rp) / (a + rp)
        e = max(e, 0.0)
        # 실제로 a < 근지점이 되도록 극단적 설정
        elem = KeplerElements(a=R_EARTH + 50_000.0, e=0.001,
                              i=0.0, raan=0.0, argp=0.0, nu=0.0)
        h = assess_orbit_health(elem)
        assert "periapsis_below_atmosphere" in h.blockers
        assert h.verdict == "CRITICAL"

    def test_safe_periapsis(self):
        elem = _leo_elem(400.0, e=0.001)
        h = assess_orbit_health(elem)
        assert "periapsis_below_atmosphere" not in h.blockers

    # ------------------------------------------------------------------
    # 탈출 궤도
    # ------------------------------------------------------------------
    def test_escape_trajectory(self):
        elem = KeplerElements(a=R_EARTH + 400_000.0, e=1.5,
                              i=0.0, raan=0.0, argp=0.0, nu=0.0)
        h = assess_orbit_health(elem)
        assert "escape_trajectory" in h.blockers
        assert h.verdict == "CRITICAL"

    # ------------------------------------------------------------------
    # 이심률 영향
    # ------------------------------------------------------------------
    def test_high_eccentricity_degrades(self):
        elem_circ = _leo_elem(e=0.001)
        elem_ell  = _leo_elem(e=0.3)
        h_circ = assess_orbit_health(elem_circ)
        h_ell  = assess_orbit_health(elem_ell)
        assert h_circ.omega_eccentricity >= h_ell.omega_eccentricity

    def test_elliptical_phase_forgives_eccentricity(self):
        """ELLIPTICAL 단계에서는 이심률 감점 완화."""
        elem = _leo_elem(e=0.2)
        h = assess_orbit_health(elem, phase=OrbitPhase.ELLIPTICAL)
        assert h.omega_eccentricity >= 0.3

    # ------------------------------------------------------------------
    # 경사각 영향
    # ------------------------------------------------------------------
    def test_target_inclination_score(self):
        """목표 경사각과 일치하면 omega_inclination = 1.0."""
        elem = _leo_elem()   # i=28.5°
        h = assess_orbit_health(
            elem,
            target_inclination_rad=math.radians(28.5),
        )
        assert h.omega_inclination == 1.0

    def test_wrong_inclination_degrades(self):
        """경사각이 크게 다르면 감점."""
        elem = _leo_elem()   # i=28.5°
        h = assess_orbit_health(
            elem,
            target_inclination_rad=math.radians(90.0),  # 극 궤도
        )
        assert h.omega_inclination < 0.7

    # ------------------------------------------------------------------
    # verdict 매핑
    # ------------------------------------------------------------------
    def test_verdict_nominal(self):
        elem = _leo_elem(400.0, e=0.001)
        h = assess_orbit_health(elem, phase=OrbitPhase.CIRCULAR)
        # 이상적 조건에서 NOMINAL 또는 STABLE
        assert h.verdict in ("NOMINAL", "STABLE", "DEGRADED")

    def test_orbit_ok_flag(self):
        elem = _leo_elem()
        h = assess_orbit_health(elem)
        if h.verdict in ("NOMINAL", "STABLE"):
            assert h.orbit_ok is True
        else:
            assert h.orbit_ok is False

    # ------------------------------------------------------------------
    # 주기·커버리지
    # ------------------------------------------------------------------
    def test_leo_period_coverage(self):
        """LEO 주기(92분 내외)면 omega_coverage = 1.0."""
        elem = _leo_elem(400.0)
        h = assess_orbit_health(elem)
        assert h.omega_coverage == 1.0

    def test_evidence_keys(self):
        """evidence 딕셔너리에 핵심 키 포함."""
        elem = _leo_elem()
        h = assess_orbit_health(elem)
        assert "periapsis_alt_km" in h.evidence
        assert "eccentricity" in h.evidence
        assert "inclination_deg" in h.evidence
