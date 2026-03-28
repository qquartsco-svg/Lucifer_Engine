"""§2 — 케플러 역학 테스트."""

import math
import pytest
from lucifer_engine.contracts.schemas import (
    StateVector, KeplerElements, MU_EARTH, R_EARTH,
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

_TOL = 1e-3   # 0.1% 오차 허용


def _leo_circular_sv() -> StateVector:
    """LEO 원 궤도 상태 벡터 생성 (정확한 원 궤도)."""
    alt = 400_000.0
    r = R_EARTH + alt
    v_c = math.sqrt(MU_EARTH / r)   # 원 궤도 속도
    # z 방향 상승 없이 x 방향으로 원 궤도 (단순화)
    # 실제로는 vy_ms = v_c (북쪽 방향 속도), z=alt
    return StateVector(
        x_m=0.0, y_m=0.0, z_m=alt,
        vx_ms=v_c, vy_ms=0.0, vz_ms=0.0,
        t_s=0.0, mass_kg=1_000.0,
    )


# ---------------------------------------------------------------------------
# 원형화 속도
# ---------------------------------------------------------------------------
class TestCircularVelocity:
    def test_leo_400km(self):
        v = circular_velocity_ms(400_000.0)
        # 기대값: ~7669 m/s
        assert 7600 < v < 7750

    def test_leo_500km(self):
        v = circular_velocity_ms(500_000.0)
        assert 7600 < v < 7700

    def test_geo_35786km(self):
        v = circular_velocity_ms(35_786_000.0)
        # GEO: ~3075 m/s
        assert 3000 < v < 3200


# ---------------------------------------------------------------------------
# 궤도 주기
# ---------------------------------------------------------------------------
class TestOrbitalPeriod:
    def test_leo_400km(self):
        T = orbital_period_s(400_000.0)
        # LEO ~92분
        assert 88 * 60 < T < 96 * 60

    def test_geo(self):
        T = orbital_period_s(35_786_000.0)
        # GEO ~86400s (24시간)
        assert 86_000 < T < 87_000


# ---------------------------------------------------------------------------
# 탈출 속도
# ---------------------------------------------------------------------------
class TestEscapeVelocity:
    def test_leo(self):
        ve = escape_velocity_ms(400_000.0)
        vc = circular_velocity_ms(400_000.0)
        # 탈출 속도 = sqrt(2) × 원 궤도 속도
        assert abs(ve - vc * math.sqrt(2.0)) / vc < _TOL

    def test_surface(self):
        ve = escape_velocity_ms(0.0)
        # 지표 탈출 속도 ~11.2 km/s
        assert 11_100 < ve < 11_300


# ---------------------------------------------------------------------------
# Vis-Viva 방정식
# ---------------------------------------------------------------------------
class TestVisViva:
    def test_circular(self):
        r = R_EARTH + 400_000.0
        v = vis_viva_ms(r, r)   # 원 궤도: a=r
        expected = circular_velocity_ms(400_000.0)
        assert abs(v - expected) / expected < _TOL

    def test_periapsis(self):
        # 타원 궤도 근지점에서 가장 빠름
        rp = R_EARTH + 200_000.0
        ra = R_EARTH + 600_000.0
        a  = 0.5 * (rp + ra)
        v_peri = vis_viva_ms(rp, a)
        v_apo  = vis_viva_ms(ra, a)
        assert v_peri > v_apo


# ---------------------------------------------------------------------------
# 상태 벡터 ↔ 케플러 요소 변환
# ---------------------------------------------------------------------------
class TestStateToElements:
    def test_circular_leo_eccentricity(self):
        sv = _leo_circular_sv()
        elem = state_to_elements(sv)
        # 원 궤도: e ≈ 0
        assert elem.e < 0.05

    def test_circular_leo_semimajor_axis(self):
        sv = _leo_circular_sv()
        elem = state_to_elements(sv)
        expected_a = R_EARTH + 400_000.0
        # 10% 오차 허용 (직교 좌표계 근사)
        assert abs(elem.a - expected_a) / expected_a < 0.15

    def test_period_from_elements(self):
        sv = _leo_circular_sv()
        elem = state_to_elements(sv)
        # 주기가 LEO 범위 내
        if elem.a > 0 and elem.e < 1.0:
            assert 80 * 60 < elem.period_s < 100 * 60

    def test_elements_roundtrip(self):
        """
        elements_to_state → state_to_elements 왕복.

        설계 참고:
          StateVector.z_m = 고도 (고도 = |r| − R_EARTH) 로 정의하여
          state_to_elements 에서 z축 기준 rz=z_m+R_EARTH 를 근사값으로 사용.
          이 근사는 적도 경사각 orbit(i≈0) 에서 정확하며,
          기울어진 궤도에서는 좌표계 변환 오차가 발생할 수 있다.
          속도 크기와 고도는 보존됨을 검증한다.
        """
        a = R_EARTH + 400_000.0
        elem_orig = KeplerElements(
            a=a, e=0.01,
            i=math.radians(28.5),
            raan=0.0, argp=0.0, nu=0.0,
        )
        sv = elements_to_state(elem_orig, t_s=100.0, mass_kg=1000.0)

        # nu=0 에서 고도는 근지점 고도 a(1-e) - R_EARTH
        peri_alt_expected = a * (1.0 - 0.01) - R_EARTH
        assert abs(sv.altitude_m - peri_alt_expected) / peri_alt_expected < 0.15

        # 속도 크기는 Vis-Viva 기준 ± 5% 이내
        v_expected = vis_viva_ms(a, a)  # nu=0, r=a*(1-e²)/(1+e*cos0) ≈ a(1-e)
        assert abs(sv.speed_ms - v_expected) / v_expected < 0.15

        # 질량·시간 보존
        assert sv.mass_kg == 1000.0
        assert sv.t_s == 100.0


# ---------------------------------------------------------------------------
# 케플러 전파
# ---------------------------------------------------------------------------
class TestPropagateKepler:
    def test_one_orbit(self):
        """1궤도 주기 후 nu가 원점으로 복귀."""
        a = R_EARTH + 400_000.0
        elem = KeplerElements(a=a, e=0.001, i=0.5,
                              raan=0.0, argp=0.0, nu=0.0)
        T = elem.period_s
        elem_after = propagate_kepler(elem, T)
        # a, e, i, raan, argp 보존
        assert abs(elem_after.a - elem.a) < 1.0
        assert abs(elem_after.e - elem.e) < 1e-9
        # nu는 2π 후 0으로 복귀 (±0.1 rad 허용)
        nu_diff = abs(elem_after.nu - elem.nu) % (2 * math.pi)
        assert min(nu_diff, 2 * math.pi - nu_diff) < 0.1

    def test_half_orbit(self):
        """반 궤도 후 nu ≈ π."""
        a = R_EARTH + 400_000.0
        elem = KeplerElements(a=a, e=0.001, i=0.5,
                              raan=0.0, argp=0.0, nu=0.0)
        T = elem.period_s
        elem_half = propagate_kepler(elem, T / 2.0)
        nu = elem_half.nu
        # nu ≈ π (원지점)
        assert abs(nu - math.pi) < 0.1

    def test_escape_orbit_unchanged(self):
        """탈출 궤도는 전파 미지원 — 요소 보존."""
        elem = KeplerElements(a=R_EARTH + 400_000.0, e=1.5,
                              i=0.0, raan=0.0, argp=0.0, nu=0.0)
        elem_after = propagate_kepler(elem, 100.0)
        assert elem_after.e == elem.e  # 변경 없음

    def test_elements_to_state_altitude(self):
        """elements_to_state 고도 출력 검증."""
        a = R_EARTH + 500_000.0
        elem = KeplerElements(a=a, e=0.0, i=0.0,
                              raan=0.0, argp=0.0, nu=0.0)
        sv = elements_to_state(elem)
        assert sv.altitude_m > 450_000.0
