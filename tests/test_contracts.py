"""§1 — 데이터 계약 테스트."""

import math
import pytest
from lucifer_engine.contracts.schemas import (
    StateVector, KeplerElements, OrbitPhase, OrbitHealthReport,
    MissionProfile, ManeuverPlan, ManeuverStep, ManeuverType,
    MU_EARTH, R_EARTH, J2,
)


# ---------------------------------------------------------------------------
# StateVector
# ---------------------------------------------------------------------------
class TestStateVector:
    def test_altitude_m(self):
        sv = StateVector(z_m=400_000.0)
        assert sv.altitude_m == 400_000.0

    def test_radius_m(self):
        sv = StateVector(z_m=400_000.0)
        assert abs(sv.radius_m - (R_EARTH + 400_000.0)) < 1.0

    def test_speed_ms(self):
        sv = StateVector(vx_ms=7_600.0, vy_ms=0.0, vz_ms=100.0)
        assert abs(sv.speed_ms - math.sqrt(7_600.0**2 + 100.0**2)) < 1e-9

    def test_specific_energy_leo(self):
        # LEO 원 궤도: v_c = sqrt(mu/r)
        r = R_EARTH + 400_000.0
        v_c = math.sqrt(MU_EARTH / r)
        sv = StateVector(z_m=400_000.0, vz_ms=v_c)
        # ε = v²/2 − μ/r 가 음수여야 함 (속박 궤도)
        assert sv.specific_energy_j_kg < 0

    def test_kinetic_energy(self):
        sv = StateVector(vx_ms=7600.0, mass_kg=1000.0)
        expected = 0.5 * 1000.0 * 7600.0**2
        assert abs(sv.kinetic_energy_j - expected) < 1.0

    def test_zero_state(self):
        sv = StateVector()
        assert sv.speed_ms == 0.0
        assert sv.altitude_m == 0.0


# ---------------------------------------------------------------------------
# KeplerElements
# ---------------------------------------------------------------------------
class TestKeplerElements:
    def _leo_elem(self) -> KeplerElements:
        a = R_EARTH + 400_000.0
        return KeplerElements(a=a, e=0.001, i=math.radians(28.5),
                              raan=0.0, argp=0.0, nu=0.0)

    def test_periapsis(self):
        e = self._leo_elem()
        assert e.periapsis_altitude_m > 390_000.0

    def test_apoapsis(self):
        e = self._leo_elem()
        assert e.apoapsis_altitude_m < 410_000.0

    def test_period(self):
        e = self._leo_elem()
        # LEO 주기 ≈ 92분
        assert 88 * 60 < e.period_s < 96 * 60

    def test_mean_motion(self):
        e = self._leo_elem()
        assert e.mean_motion_rad_s > 0.0

    def test_is_circular(self):
        e = KeplerElements(a=R_EARTH + 400_000.0, e=0.005,
                           i=0.0, raan=0.0, argp=0.0, nu=0.0)
        assert e.is_circular

    def test_not_circular(self):
        e = KeplerElements(a=R_EARTH + 400_000.0, e=0.1,
                           i=0.0, raan=0.0, argp=0.0, nu=0.0)
        assert not e.is_circular

    def test_is_escape(self):
        e = KeplerElements(a=R_EARTH + 400_000.0, e=1.1,
                           i=0.0, raan=0.0, argp=0.0, nu=0.0)
        assert e.is_escape

    def test_inclination_deg(self):
        e = self._leo_elem()
        assert abs(e.inclination_deg - 28.5) < 0.01

    def test_circular_velocity(self):
        a = R_EARTH + 400_000.0
        e = KeplerElements(a=a, e=0.0, i=0.0, raan=0.0, argp=0.0, nu=0.0)
        expected = math.sqrt(MU_EARTH / a)
        assert abs(e.circular_velocity_ms - expected) < 0.1


# ---------------------------------------------------------------------------
# MissionProfile
# ---------------------------------------------------------------------------
class TestMissionProfile:
    def test_target_radius(self):
        m = MissionProfile(target_altitude_m=400_000.0)
        assert abs(m.target_radius_m - (R_EARTH + 400_000.0)) < 1.0

    def test_circular_velocity(self):
        m = MissionProfile(target_altitude_m=400_000.0)
        r = R_EARTH + 400_000.0
        expected = math.sqrt(MU_EARTH / r)
        assert abs(m.target_circular_velocity_ms - expected) < 0.1

    def test_defaults(self):
        m = MissionProfile()
        assert m.target_altitude_m == 400_000.0
        assert m.payload_mass_kg == 1_000.0


# ---------------------------------------------------------------------------
# ManeuverPlan
# ---------------------------------------------------------------------------
class TestManeuverPlan:
    def test_n_burns(self):
        s1 = ManeuverStep(ManeuverType.CIRCULARIZE, 100.0, 10.0)
        s2 = ManeuverStep(ManeuverType.HOHMANN, 50.0, 5.0)
        plan = ManeuverPlan(steps=(s1, s2), total_delta_v_ms=150.0)
        assert plan.n_burns == 2

    def test_empty_plan(self):
        plan = ManeuverPlan()
        assert plan.n_burns == 0
        assert plan.total_delta_v_ms == 0.0


# ---------------------------------------------------------------------------
# 상수 검증
# ---------------------------------------------------------------------------
class TestConstants:
    def test_mu_earth(self):
        assert abs(MU_EARTH - 3.986e14) / 3.986e14 < 0.01

    def test_r_earth(self):
        assert 6_350_000.0 < R_EARTH < 6_400_000.0

    def test_j2(self):
        assert 1.08e-3 < J2 < 1.09e-3
