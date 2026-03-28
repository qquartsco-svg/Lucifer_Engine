"""
Lucifer_Engine — 궤도 역학 데이터 계약

레이어:
  L1 데이터 계약 — 모든 상위 레이어는 이 스키마만 의존.
  stdlib 전용, 외부 의존성 없음.

단위 규칙:
  거리: 미터 (m)
  속도: m/s
  각도: 라디안 (rad) — 내부 계산
  질량: kg
  시간: 초 (s)
  에너지: J (줄)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Tuple


# ---------------------------------------------------------------------------
# 지구 상수 (WGS-84 근사)
# ---------------------------------------------------------------------------
MU_EARTH: float = 3.986_004_418e14   # 표준 중력 상수 (m³/s²)
R_EARTH:  float = 6_371_000.0         # 지구 평균 반지름 (m)
J2:       float = 1.082_63e-3         # J2 항 (세차 계산용)
OMEGA_EARTH: float = 7.292_115e-5     # 지구 자전 각속도 (rad/s)


# ---------------------------------------------------------------------------
# 1. 궤도 단계 FSM
# ---------------------------------------------------------------------------
class OrbitPhase(Enum):
    """궤도 운용 단계 FSM."""
    INJECTION        = "injection"        # NOMINAL 상태 수신, 궤도 요소 계산 중
    ELLIPTICAL       = "elliptical"       # 타원 궤도 — 원형화 기동 필요
    CIRCULARIZING    = "circularizing"    # 원형화 번 실행 중
    CIRCULAR         = "circular"         # 원 궤도 안정 상태
    MANEUVERING      = "maneuvering"      # Hohmann / 면 변경 기동 중
    STATION_KEEPING  = "station_keeping"  # 궤도 유지 단계
    DEORBIT_BURN     = "deorbit_burn"     # 재진입 기동
    REENTRY          = "reentry"          # 재진입 개시
    NOMINAL          = "nominal"          # 목표 궤도 안정 도달
    ABORT            = "abort"            # 궤도 이탈 / 비상


# ---------------------------------------------------------------------------
# 2. 상태 벡터 (State Vector) — Rocket_Spirit 인터페이스
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class StateVector:
    """
    3D 직교 좌표계 상태 벡터 (ECI 근사 — 발사장 중심).

    Rocket_Spirit `RocketState` 와 1:1 대응.
    x_m : 동쪽 (East), y_m : 북쪽 (North), z_m : 상향 (Up)
    """
    x_m:    float = 0.0   # East (m)
    y_m:    float = 0.0   # North (m)
    z_m:    float = 0.0   # Up — 발사장 해발 기준 (m)
    vx_ms:  float = 0.0   # East 속도 (m/s)
    vy_ms:  float = 0.0   # North 속도 (m/s)
    vz_ms:  float = 0.0   # Up 속도 (m/s)
    t_s:    float = 0.0   # 발사 후 경과 시간 (s)
    mass_kg: float = 0.0  # 현재 차량 질량 (kg) — 페이로드 only

    @property
    def radius_m(self) -> float:
        """지구 중심에서의 거리 r = R_Earth + z_m."""
        return R_EARTH + self.z_m

    @property
    def speed_ms(self) -> float:
        """속도 크기 |v|."""
        return math.sqrt(self.vx_ms**2 + self.vy_ms**2 + self.vz_ms**2)

    @property
    def altitude_m(self) -> float:
        """지표면 기준 고도 (m)."""
        return self.z_m

    @property
    def kinetic_energy_j(self) -> float:
        v = self.speed_ms
        return 0.5 * self.mass_kg * v * v if self.mass_kg > 0 else 0.0

    @property
    def specific_energy_j_kg(self) -> float:
        """비 에너지 ε = v²/2 − μ/r  (J/kg)."""
        r = self.radius_m
        v = self.speed_ms
        return 0.5 * v * v - MU_EARTH / r if r > 0 else 0.0


# ---------------------------------------------------------------------------
# 3. 케플러 궤도 요소 (Classical Orbital Elements)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class KeplerElements:
    """
    고전 케플러 궤도 6요소.

    a  : 반장축 (m)
    e  : 이심률 (무차원) 0=원, 0<e<1=타원, 1=포물선
    i  : 궤도경사각 (rad)
    raan : 승교점 적경 Ω (rad)
    argp : 근지점 편각 ω (rad)
    nu   : 진근점 이각 ν (rad)
    """
    a:    float   # 반장축 (m)
    e:    float   # 이심률
    i:    float   # 경사각 (rad)
    raan: float   # 승교점 적경 (rad)
    argp: float   # 근지점 편각 (rad)
    nu:   float   # 진근점 이각 (rad)

    @property
    def periapsis_m(self) -> float:
        """근지점 거리 rp = a(1−e) — 지구 중심 기준 (m)."""
        return self.a * (1.0 - self.e)

    @property
    def apoapsis_m(self) -> float:
        """원지점 거리 ra = a(1+e) — 지구 중심 기준 (m)."""
        return self.a * (1.0 + self.e)

    @property
    def periapsis_altitude_m(self) -> float:
        """근지점 고도 (m)."""
        return self.periapsis_m - R_EARTH

    @property
    def apoapsis_altitude_m(self) -> float:
        """원지점 고도 (m)."""
        return self.apoapsis_m - R_EARTH

    @property
    def period_s(self) -> float:
        """궤도 주기 T = 2π√(a³/μ) (s)."""
        if self.a <= 0:
            return 0.0
        return 2.0 * math.pi * math.sqrt(self.a**3 / MU_EARTH)

    @property
    def mean_motion_rad_s(self) -> float:
        """평균 운동 n = √(μ/a³) (rad/s)."""
        if self.a <= 0:
            return 0.0
        return math.sqrt(MU_EARTH / self.a**3)

    @property
    def circular_velocity_ms(self) -> float:
        """반장축 기준 원 궤도 속도 (m/s)."""
        if self.a <= 0:
            return 0.0
        return math.sqrt(MU_EARTH / self.a)

    @property
    def inclination_deg(self) -> float:
        return math.degrees(self.i)

    @property
    def is_circular(self) -> bool:
        """이심률 < 0.01 이면 실질적 원 궤도."""
        return self.e < 0.01

    @property
    def is_escape(self) -> bool:
        """이심률 ≥ 1 이면 탈출 궤도."""
        return self.e >= 1.0


# ---------------------------------------------------------------------------
# 4. 기동 계획 (Maneuver Plan)
# ---------------------------------------------------------------------------
class ManeuverType(Enum):
    CIRCULARIZE    = "circularize"     # 원형화 번
    HOHMANN        = "hohmann"         # 호만 전이 (두 원 궤도 사이)
    PLANE_CHANGE   = "plane_change"    # 궤도면 변경
    DEORBIT        = "deorbit"         # 재진입 기동
    STATION_KEEP   = "station_keep"    # 궤도 유지


@dataclass(frozen=True)
class ManeuverStep:
    """단일 기동 스텝 — 특정 위상에서 ΔV 적용."""
    maneuver_type:  ManeuverType
    delta_v_ms:     float          # ΔV 크기 (m/s)
    burn_duration_s: float         # 연소 시간 (s) — 추정
    true_anomaly_rad: float = 0.0  # 실행 위상 (rad)
    description:    str = ""


@dataclass(frozen=True)
class ManeuverPlan:
    """기동 계획 전체 — 하나 이상의 ManeuverStep으로 구성."""
    steps:           Tuple[ManeuverStep, ...] = ()
    total_delta_v_ms: float = 0.0
    total_duration_s: float = 0.0
    target_altitude_m: float = 0.0
    target_inclination_rad: float = 0.0

    @property
    def n_burns(self) -> int:
        return len(self.steps)


# ---------------------------------------------------------------------------
# 5. 궤도 건강도 (Orbit Health — Ω 스코어)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class OrbitHealthReport:
    """
    궤도 건강도 종합 판정 (Ω 가중 스코어).

    각 컴포넌트:
      omega_periapsis  — 근지점이 대기권(80km) 이상인지
      omega_energy     — 비 에너지가 음수(타원)인지
      omega_eccentricity — 이심률이 목표 허용 범위 내인지
      omega_inclination — 목표 경사각과의 오차
      omega_coverage   — 궤도 주기·고도 조합 임무 적합성
      omega_total      — 가중 합산
    """
    omega_periapsis:    float = 0.0
    omega_energy:       float = 0.0
    omega_eccentricity: float = 0.0
    omega_inclination:  float = 0.0
    omega_coverage:     float = 0.0
    omega_total:        float = 0.0

    phase:   OrbitPhase = OrbitPhase.INJECTION
    verdict: str = "UNKNOWN"        # "NOMINAL" | "STABLE" | "DEGRADED" | "CRITICAL"
    blockers: Tuple[str, ...] = ()
    evidence: dict = field(default_factory=dict)

    @property
    def orbit_ok(self) -> bool:
        return self.verdict in ("NOMINAL", "STABLE")


# ---------------------------------------------------------------------------
# 6. 전파 결과 (Propagation Result)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PropagationResult:
    """궤도 전파 한 스텝 결과."""
    t_s:        float            # 시뮬 시간 (s)
    state:      StateVector      # 위치·속도 벡터
    elements:   KeplerElements   # 케플러 요소
    phase:      OrbitPhase       # 현재 궤도 단계
    health:     OrbitHealthReport  # Ω 건강도
    event:      str = ""         # 주요 이벤트 로그


# ---------------------------------------------------------------------------
# 7. 임무 프로파일 (Mission Profile)
# ---------------------------------------------------------------------------
@dataclass
class MissionProfile:
    """
    Lucifer_Engine 임무 목표 정의.

    target_altitude_m  : 목표 원 궤도 고도 (m) — LEO 기본 400km
    target_inclination_deg : 목표 경사각 (도)
    payload_mass_kg    : 페이로드 질량 (kg)
    max_delta_v_ms     : 사용 가능한 최대 ΔV (m/s)
    """
    target_altitude_m:     float = 400_000.0   # 400 km LEO
    target_inclination_deg: float = 28.5        # 케네디 우주센터 위도
    payload_mass_kg:       float = 1_000.0
    max_delta_v_ms:        float = 1_500.0      # 궤도 기동용 ΔV 예산
    isp_s:                 float = 320.0        # 상단 엔진 비추력 (s)
    dry_mass_kg:           float = 500.0        # 상단 구조 건질량 (kg)

    @property
    def target_radius_m(self) -> float:
        return R_EARTH + self.target_altitude_m

    @property
    def target_circular_velocity_ms(self) -> float:
        return math.sqrt(MU_EARTH / self.target_radius_m)
