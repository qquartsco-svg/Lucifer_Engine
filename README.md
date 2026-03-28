# Lucifer_Engine

> **English:** [README_EN.md](README_EN.md)

루시퍼의 추락은 자유 낙하가 아니었다.
그것은 궤도였다. 계산된 곡선. 돌아오지 않을 것을 알고도 그린 포물선.

이 엔진은 그 궤도를 계산한다.

`Lucifer_Engine` 은 브랜딩 이름이다. 실제 패키지 이름은 `lucifer_engine` 이다.

---

## 무엇인가

`Lucifer_Engine` 은 `Rocket_Spirit` 발사체가 MECO(주엔진 연소 종료) 이후
궤도 삽입 단계(NOMINAL)에서 인계하는 **궤도 전파·기동·건강도 판정 엔진**이다.

```
Rocket_Spirit NOMINAL 출구 (h=444km, v≈7.6km/s)
        ↓  StateVector 핸드오프
Lucifer_Engine
  ├── 케플러 요소 계산 (a, e, i, Ω, ω, ν)
  ├── 궤도 건강도 판정 (Ω 5개 컴포넌트)
  ├── 기동 계획 (원형화, 호만 전이, 면 변경, 재진입)
  ├── 궤도 전파 (Kepler + J2 섭동)
  └── NOMINAL 도달 판정
```

---

## Rocket_Spirit 연결 (v0.1.0)

```python
from lucifer_engine import OrbitAgent, MissionProfile
from lucifer_engine import state_vector_from_rocket_spirit

# Rocket_Spirit NOMINAL 상태 수신
sv = state_vector_from_rocket_spirit(rocket_state)

# 궤도 에이전트 초기화
mission = MissionProfile(target_altitude_m=444_000.0)
agent = OrbitAgent(mission)

# 궤도 삽입 → 기동 계획 → NOMINAL 도달
health = agent.inject(sv)
plan   = agent.plan_maneuvers()
success, results = agent.run_to_nominal(max_steps=200, dt_s=60.0)

print(agent.summary())
```

---

## 레이어 구조

```
lucifer_engine/
├── contracts/schemas.py     — StateVector, KeplerElements, OrbitPhase,
│                              OrbitHealthReport, MissionProfile, ManeuverPlan
├── mechanics/
│   ├── kepler.py            — 상태 벡터 ↔ 케플러 요소, 전파, Vis-Viva
│   ├── maneuvers.py         — 원형화 번, 호만 전이, 면 변경, 재진입 번
│   └── propagator.py        — Kepler 전파, J2 섭동 전파, 단일 스텝
├── health/orbit_health.py   — Ω 5요소 건강도 판정
├── bridges/
│   └── rocket_spirit_bridge.py — Rocket_Spirit 어댑터 (duck-type)
└── agent/orbit_agent.py     — OrbitAgent, OrbitChain (SHA-256 감사 추적)
```

---

## 궤도 단계 FSM (11상태)

```
INJECTION → ELLIPTICAL → CIRCULARIZING → CIRCULAR
         → MANEUVERING → STATION_KEEPING → NOMINAL
         → DEORBIT_BURN → REENTRY
         (언제든) → ABORT
```

---

## Ω 건강도 (5개 컴포넌트)

| 컴포넌트 | 가중치 | 설명 |
|---------|-------|------|
| `ω_periapsis` | 0.30 | 근지점 고도 ≥ 80km (대기권 임계) |
| `ω_energy` | 0.25 | 비 에너지 음수 (속박 궤도) |
| `ω_eccentricity` | 0.20 | 이심률 목표 범위 내 |
| `ω_inclination` | 0.15 | 목표 경사각 오차 |
| `ω_coverage` | 0.10 | 주기·고도 임무 적합성 |

**verdict**: `NOMINAL` (Ω≥0.90) / `STABLE` (≥0.75) / `DEGRADED` (≥0.55) / `CRITICAL`

---

## 지원 기동

| 기동 | 설명 | ΔV 기준 |
|------|------|---------|
| **원형화 번** | 타원 → 원 궤도 (원지점에서) | 수십~수백 m/s |
| **호만 전이** | 두 원 궤도 사이 최적 전이 | LEO↔GEO ≈ 3.9 km/s |
| **궤도면 변경** | 경사각 조정 | 2·v·sin(Δi/2) |
| **재진입 번** | 근지점을 대기권 내로 낮춤 | 수십~수백 m/s |

---

## J2 섭동

`use_j2=True` 시 LEO에서 두드러지는 **RAAN 세차·근지점 세차** 포함:

```
dΩ/dt = −(3/2)·n·J2·(R⊕/p)²·cos(i)   ← RAAN 서쪽 표류
dω/dt = (3/4)·n·J2·(R⊕/p)²·(5cos²i−1)  ← 근지점 편각 세차
```

---

## 테스트

```bash
cd Lucifer_Engine
python -m pytest tests/ -v
```

현재 결과: **133 passed**

| 섹션 | 내용 |
|------|------|
| §1 | 데이터 계약 (StateVector, KeplerElements, MissionProfile) |
| §2 | 케플러 역학 (변환, 전파, Vis-Viva) |
| §3 | 궤도 기동 (원형화, 호만, 면 변경, 재진입, 예산) |
| §4 | 궤도 건강도 Ω 판정 |
| §5 | 전파기 (Kepler, J2, 단일 스텝) |
| §6 | Rocket_Spirit 브리지 (dict, duck-type, tuple) |
| §7 | OrbitAgent 통합 + OrbitChain SHA-256 |

---

## 로드맵

- `v0.1.0`: 현재 — 케플러 전파, 기동 계획, Ω 건강도, Rocket_Spirit 브리지
- `v0.2.0`: TLE 입력 지원 (Two-Line Element)
- `v0.3.0`: Monte Carlo ΔV 분산 분석
- `v0.4.0`: 재사용 발사체 귀환 궤도 (반재진입, 역추진)
- `v0.5.0`: 다중 위성 성좌 배치

---

## 에코시스템 위치

```
[Wheelchair] → WTS 변형 → TAM/StarScream → Rocket_Spirit → Lucifer_Engine
                                                     (발사→궤도삽입)   (궤도 운용)
```

`Lucifer_Engine` 은 `Rocket_Spirit` 의 **v0.2.0 연동 대상** 엔진이다.
