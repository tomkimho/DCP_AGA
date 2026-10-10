# Random Plate — 프로젝트 기획서 v2.0

> **문서 버전:** v2.0.0 (Buildable)
> **작성일:** 2026-08-18
> **대체 문서:** v1.0.0 "Random Plate Pro 마스터 플랜" (폐기)
> **문서 성격:** 검증 가설 정의 / 기능 명세 / 시스템 설계 / 실행 계획

---

## 0. v1.0 → v2.0 변경 요약

v1.0은 문서 완성도는 높았으나 핵심 차별화 기능 다수가 **획득 불가능한 데이터**에 의존하고 있어 착수 시 3주차에 좌초가 확정적이었습니다. v2.0은 "구현 가능한 것만 남긴다"를 유일한 편집 원칙으로 재작성했습니다.

| v1.0 항목 | v2.0 판정 | 사유 |
|---|---|---|
| 구글 통계 혼잡도 (Popular Times) | **삭제** | Places API 공식 스펙에 해당 필드가 없음. 스크래핑은 ToS 위반 + 불안정 |
| 실시간 인앱 혼잡도 (반경 5km N팀) | **삭제** | 대규모 동시 사용자가 전제. 출시 후 장기간 항상 "0팀" 표시 |
| 회식/동창회 테마 (룸 형태·수용인원·주차) | **삭제** | 어떤 공개 API에도 없는 필드. 자체 수집은 별도 사업 규모 |
| Google Places 주 데이터 소스 | **교체** | 국내 커버리지 열세 + 리롤 1회당 과금. → 카카오 로컬 API |
| 게임 UI 4종 (룰렛/슬롯/화살표/카드) | **1종으로 축소** | 유저 가치 동일, 개발 비용 4배 |
| Google OAuth + 6자리 PIN | **삭제** | OAuth 위에 PIN은 보안 이득 0, 전환율만 하락 |
| Redis/Upstash Geo 카운터 | **삭제** | 삭제된 기능(인앱 혼잡도) 전용 인프라 |
| 날씨 / 풀코스 카페 경로 | **v1.1 이후로 이연** | 핵심 가설과 무관. 초기 복잡도만 증가 |
| 수익모델 3종 (광고/제휴/B2B) | **조건부 이연** | 전부 MAU 10만 이후 시나리오. v0 수익 목표 = 0원 |
| 4~5주 완성 일정 | **재산정** | v1.0 범위 기준 실제 3~4개월. v2.0 축소 범위 기준 2주 |
| — | **신규 추가** | 유저 획득/재방문 설계, API 비용 모델, 위치정보 법적 검토, 검증 지표 및 중단 기준 |

---

## 1. 제품 정의

### 1.1 한 줄 정의

**링크 하나로 팀이 같이 점심 메뉴를 정하는 웹앱.** 로그인 없음, 설치 없음.

### 1.2 검증할 단 하나의 가설

> **"링크로 방을 만들어 다 같이 뽑고 투표하는 것이, 카톡방에서 링크 던지며 눈치보는 것보다 낫다."**

이 가설이 참이면 나머지 기능(혼잡도·예약·아카이브·수익화)은 그 위에 올릴 수 있습니다. 거짓이면 어떤 기능도 의미가 없습니다. **v0의 목적은 기능 완성이 아니라 이 문장의 참/거짓 판정입니다.**

### 1.3 타깃 (범위 축소)

- **1차:** 3~8인 규모로 매일 같이 점심 먹는 직장인 팀. 특히 "메뉴 정하기"를 맡게 되는 팀 내 총무 역할자.
- v1.0의 회식·동창회·데이트 타깃은 v0 범위에서 제외합니다. 데이터가 없어 차별화가 불가능하고, 사용 빈도가 낮아(연 1~2회) 재방문 검증에 부적합합니다.

### 1.4 비(非)목표 — 명시적으로 하지 않는 것

v0에서 아래는 **의식적으로 만들지 않습니다.** 요청이 들어와도 v0 종료 전까지는 거절합니다.

- 회원가입, 로그인, 마이페이지, 방문 기록 저장
- 혼잡도, 웨이팅, 예약 연동
- 평점/리뷰 자체 표기 (→ 카카오맵 딥링크로 위임)
- 네이티브 앱, PWA 푸시
- 광고, 결제, 정산
- 관리자 대시보드

---

## 2. 경쟁 및 차별화 (현실 인식)

### 2.1 시장 상태

"점심 메뉴 룰렛"은 이미 국내외에 수십 개 존재하는 **레드오션이자 저(低)해자 영역**입니다. 개인 개발자 토이 프로젝트부터 상용 앱까지 포화 상태이며, 단순 룰렛만으로는 어떤 차별점도 없습니다.

### 2.2 v1.0의 차별화 전략이 실패한 이유

v1.0은 해자를 **데이터**(혼잡도, 룸 정보)에서 찾았습니다. 방향 자체는 옳았으나, 그 데이터를 확보할 방법이 없었습니다. 확보 불가능한 자원 위에 세운 차별화는 차별화가 아니라 희망사항입니다.

### 2.3 v2.0의 차별화 전략

해자를 데이터가 아니라 **협업 흐름(collaboration flow)** 에서 찾습니다.

| 구분 | 기존 룰렛 앱 | Random Plate v0 |
|---|---|---|
| 사용 단위 | 개인 1명 | 팀 N명 |
| 결과 | 나 혼자 봄 → 다시 카톡에 옮겨 설명 | 팀 전원이 같은 화면을 실시간으로 봄 |
| 의사결정 | 뽑은 사람이 통보 | 전원 1인 1표 투표로 확정 |
| 진입 장벽 | 앱 설치 or 로그인 | 링크 클릭 1회 |

**"혼자 쓰는 룰렛"이 아니라 "여러 명이 같이 쓰는 링크"** 라는 점 하나가 전부입니다. 이건 데이터 없이, 무료로, 2주 안에 만들 수 있고 — 그래서 실제로 검증할 수 있습니다.

### 2.4 여전히 남는 리스크 (숨기지 않음)

이 차별점은 **모방 난이도가 낮습니다.** 경쟁사가 마음먹으면 2주면 따라옵니다. 방어 수단은 선점 속도와, 검증 이후 쌓을 팀 단위 사용 이력(누적 이력이 쌓일수록 "안 먹은 곳" 추천 품질이 올라가는 구조)뿐입니다. 이 리스크를 감수하고 시작할지는 의사결정 사항입니다.

---

## 3. 데이터 소스 결정 (v2.0 핵심 변경)

### 3.1 카카오 로컬 API를 주 소스로 채택

| 항목 | Google Places API (New) | 카카오 로컬 API |
|---|---|---|
| 국내 식당 커버리지 | 보통 (누락·구정보 다수) | 우수 |
| 과금 | 호출당 유료 | 무료 쿼터 내 무료 |
| 평점/리뷰 | 제공 (해외 중심 품질) | **미제공** |
| 영업시간 | 일부 제공 | **미제공** |
| 메뉴/가격 | **미제공** | **미제공** |
| 혼잡도 | **미제공** (v1.0의 오해) | 미제공 |
| 상세 페이지 연결 | Google Maps 링크 | `place_url` (카카오맵 딥링크) |

**결정:** 카카오 로컬 API의 `카테고리로 장소 검색`(category_group_code=`FD6` 음식점) + 좌표/반경 필터를 v0 유일 데이터 소스로 사용합니다.

> ⚠️ **착수 전 확인 필요:** 카카오 개발자 콘솔의 현행 일일 쿼터 한도와 상업적 이용 조건, 그리고 `place_url` 딥링크 사용 시 카카오 서비스 약관상 제약을 반드시 문서로 확인하고 이 문단을 실제 수치로 갱신할 것. (v1.0의 실패 원인이 정확히 "API 스펙을 확인하지 않고 기획한 것"이므로, 이 확인은 Day 1의 첫 작업입니다.)

### 3.2 평점이 없는 문제를 어떻게 다루는가

v0에서는 **평점을 표시하지 않습니다.** 대신:

- 후보 카드에는 **상호명 / 카테고리 / 도보 거리**만 표시합니다.
- "카카오맵에서 보기" 버튼으로 `place_url`을 새 창에 엽니다. 평점·사진·리뷰 확인은 카카오맵에 위임합니다.

이는 타협이지만 합리적입니다 — 애초에 랜덤 추천 제품에서 사용자가 원하는 건 "결정을 대신 내려주는 것"이지 "정보 비교"가 아닙니다. 정보 비교를 원하는 순간 사용자는 이미 카카오맵/네이버로 갑니다.

**향후 옵션(v1.1):** 확정된 승리 식당 **1곳에 대해서만** Google Places Text Search로 평점을 1회 조회하고 7일 캐싱. 방 1개당 최대 1콜이므로 비용이 통제됩니다.

### 3.3 캐싱 전략 — 리롤 비용을 0으로 만드는 설계

v1.0의 최대 비용 리스크는 "리롤(다시 돌리기)이 곧 API 호출"이라는 구조였습니다. v2.0은 구조 자체를 바꿉니다.

```
1) 방 생성 시 단 1회: 중심좌표 → geohash6(약 1.2km × 0.6km 격자)로 반올림
2) place_cache 조회 → HIT면 API 호출 없음 / MISS면 카카오 API 1~2콜 후 저장 (TTL 7일)
3) 후보 풀(최대 45곳)을 방에 고정
4) 리롤·재추첨·참가자 N명의 개별 스핀 = 전부 이 고정 풀 안에서 클라이언트 셔플 → API 호출 0
```

**결과:** API 호출량이 `방 생성 수`에 비례하고 `사용자 수 × 리롤 횟수`와 무관해집니다. 같은 오피스 밀집 지역에서는 격자 캐시 히트로 호출이 사실상 0에 수렴합니다.

---

## 4. 기능 명세 (v0 범위)

화면은 **4개**입니다. 그 이상은 v0가 아닙니다.

### 4.1 Screen 1 — 시작 화면 `/`

- 카피 1줄 + [혼자 뽑기] / [같이 정하기] 버튼 2개
- **위치 획득 (2단계로 축소)**
  - Level 1: `navigator.geolocation` 호출
  - Level 2: 거부/실패 시 주소·역명 검색 입력창 (카카오 키워드 검색 API)
  - *(v1.0의 IP 지오로케이션, 로그인 유저 프리셋은 삭제 — 로그인이 없고, IP 기반은 시/구 단위라 도보 거리 계산에 무용)*
- 반경 선택: 도보 5분(400m) / 10분(800m) / 15분(1200m) — 기본 800m
- **테마 삭제.** 시간대로 자동 판별만 합니다(11~15시=점심, 그 외=저녁). 필터 로직은 동일하고 카피만 바뀝니다.

### 4.2 Screen 2 — 룰렛 `/spin` · `/room/[code]`

- **룰렛 1종만.** 슬롯머신·화살표·카드뒤집기는 만들지 않습니다.
- 8칸 휠, 후보 풀에서 8곳 샘플링 → 스핀 → 1곳 당첨
- [다시 돌리기] 무제한 (API 호출 0, 고정 풀 내 재샘플링)
- **혼자 뽑기 모드:** 당첨 → Screen 4로 직행
- **같이 정하기 모드:** 참가자 각자 스핀 → 전원 결과 집계 → **중복 최다 Top 3** 자동 선정 → Screen 3
  - 3명 미만이거나 중복이 없으면 각자 결과를 그대로 후보로 사용(최대 5개)

### 4.3 Screen 3 — 실시간 투표 `/room/[code]/vote`

- 후보 카드 3~5장: 상호명 / 카테고리 / 도보 거리 / [카카오맵] 링크
- **1인 1표** — DB `UNIQUE(room_id, participant_id)` 제약으로 하드 보장 (재투표는 변경으로 처리)
- 실시간 득표 게이지 (Supabase Realtime)
- **타이머 60초 고정** (v1.0의 30/60초 선택 삭제 — 설정 화면 하나를 없애는 값어치가 더 큼)
- 마감 시 1위 확정 → Confetti
- **동점 처리:** v0는 동점 후보 중 **서버 시드 기반 무작위 1곳 선택** 후 "동전 던지기로 결정!" 문구 표시. (v1.0의 "결선 룰렛 자동 전환"은 상태 머신을 한 단계 더 만들어야 하므로 v1.1로 이연)

### 4.4 Screen 4 — 결과 `/room/[code]/result` · `/result/[id]`

- 확정 식당 1곳: 상호명 / 카테고리 / 도보 거리 / 지도 미리보기 / [카카오맵 길찾기] / [전화]
- [카카오톡 공유] — 동적 OG 이미지(`@vercel/og`)
- [다시 정하기] → Screen 1

### 4.5 유저 획득 및 재방문 설계 (v1.0 누락분 — 가장 중요)

v1.0에는 "어떻게 알리고 어떻게 다시 오게 할 것인가"가 통째로 없었습니다. 무로그인 웹앱은 푸시도 홈 아이콘도 없어 **재방문 훅이 구조적으로 부재**하며, 이것이 이 제품의 진짜 난이도입니다.

**획득 (전부 무료 채널):**
1. **제품 자체가 유통 채널** — 호스트 1명이 방을 만들면 링크가 팀 카톡방에 뿌려집니다. 방 1개당 3~8명 노출. 이것이 유일하면서 가장 강력한 획득 경로이며, 그래서 "공유 링크의 첫인상"(OG 카드 + 로딩 속도)이 v0 최우선 품질 항목입니다.
2. 직장인 커뮤니티(블라인드, 리멤버 커뮤니티 등) 및 개발자 커뮤니티 자발적 공유
3. `점심 메뉴 추천`, `점심 룰렛` 키워드 SEO — Next.js SSR로 기본만 확보

**재방문 (v0에서 실제로 할 수 있는 것):**
- **결과 화면에 "내일도 이 팀으로" 버튼** → 동일 참가자·동일 반경으로 방을 즉시 재생성하는 URL을 카톡에 재공유. 팀 카톡방에 링크가 남아 있는 한, 그 링크가 곧 재방문 경로입니다.
- **호스트 브라우저에 localStorage로 최근 방 설정 저장** → 재접속 시 1탭으로 방 생성
- 그 이상(푸시 알림, 정기 리마인더)은 로그인·PWA가 필요하므로 v0 범위 밖입니다. **재방문율이 낮게 나온다면 그것 자체가 유효한 검증 결과**이며, 가설 수정 신호로 취급합니다.

---

## 5. 시스템 아키텍처

```
[Client]  Next.js 15 App Router · TypeScript · Tailwind · Framer Motion
             │
             │ Server Actions / Route Handlers  (모든 쓰기는 서버 경유)
             ▼
[Vercel]  Edge/Node Functions · @vercel/og · Vercel Analytics
             │
             ├─► Supabase Postgres  (RLS: anon 쓰기 전면 차단)
             ├─► Supabase Realtime  (votes / candidates 변경 스트림)
             └─► 카카오 로컬 API    (방 생성 시 1회, place_cache 경유)
```

**스택 선정 사유:** v1.0의 스택 선택 자체는 타당했으므로 유지합니다. 단 **Redis/Upstash는 제거**합니다(해당 기능 삭제). 캐시는 Postgres 테이블로 충분하며, 인프라 구성요소를 하나 줄이는 것이 v0에서는 순이익입니다.

---

## 6. 데이터베이스 설계 (v2.0 — 전면 재작성)

v1.0 스키마의 치명적 결함 4가지를 수정했습니다: ① `votes` 테이블 부재로 1인 1표 강제 불가 ② `vote_count` 직접 증감의 경쟁 상태 ③ 방 만료 정책 부재 ④ 추측 가능한 room_code.

### 6.1 DDL

```sql
create extension if not exists pgcrypto;

-- 1) 방
create table rooms (
  id                  uuid primary key default gen_random_uuid(),
  code                text        not null unique,          -- nanoid(10), 추측 불가
  host_token_hash     text        not null,                 -- 호스트 권한 확인용 (원문 미저장)
  center_lat          numeric(6,3) not null,                -- 소수점 3자리 = 약 110m 격자로 반올림
  center_lng          numeric(7,3) not null,                -- 정밀 위치 미저장 (§9 참조)
  radius_m            int         not null default 800
                       check (radius_m between 200 and 3000),
  status              text        not null default 'spinning'
                       check (status in ('spinning','voting','closed')),
  timer_ends_at       timestamptz,                          -- 서버 권위 마감 시각
  winner_candidate_id uuid,                                 -- FK는 아래에서 추가
  expires_at          timestamptz not null default now() + interval '24 hours',
  created_at          timestamptz not null default now()
);

-- 2) 참가자 (무로그인 — 익명 토큰 해시로 식별)
create table participants (
  id          uuid primary key default gen_random_uuid(),
  room_id     uuid not null references rooms(id) on delete cascade,
  token_hash  text not null,                                -- 클라이언트 랜덤 토큰의 SHA-256
  nickname    text check (char_length(nickname) <= 20),
  created_at  timestamptz not null default now(),
  unique (room_id, token_hash)
);

-- 3) 후보 식당
create table candidates (
  id                uuid primary key default gen_random_uuid(),
  room_id           uuid not null references rooms(id) on delete cascade,
  provider          text not null default 'kakao',
  provider_place_id text not null,
  name              text not null,
  category          text,
  road_address      text,
  place_url         text,
  lat               numeric(9,6),
  lng               numeric(9,6),
  distance_m        int,
  position          smallint not null,
  unique (room_id, provider_place_id)                       -- 같은 방 내 중복 후보 차단
);

alter table rooms
  add constraint rooms_winner_fk
  foreign key (winner_candidate_id) references candidates(id) on delete set null;

-- 4) 투표 — 1인 1표를 DB 제약으로 하드 보장
create table votes (
  id             uuid primary key default gen_random_uuid(),
  room_id        uuid not null references rooms(id) on delete cascade,
  participant_id uuid not null references participants(id) on delete cascade,
  candidate_id   uuid not null references candidates(id) on delete cascade,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  unique (room_id, participant_id)                          -- ★ 핵심 제약
);

-- 5) 각자 스핀 결과 (Top 3 집계용)
create table spins (
  id             uuid primary key default gen_random_uuid(),
  room_id        uuid not null references rooms(id) on delete cascade,
  participant_id uuid not null references participants(id) on delete cascade,
  candidate_key  text not null,                             -- provider_place_id
  created_at     timestamptz not null default now(),
  unique (room_id, participant_id)                          -- 1인 1스핀 결과
);

-- 6) 장소 캐시 (API 호출량을 방 생성 수에 고정)
create table place_cache (
  geohash6       text        not null,
  category_group text        not null,
  radius_bucket  int         not null,
  payload        jsonb       not null,
  fetched_at     timestamptz not null default now(),
  primary key (geohash6, category_group, radius_bucket)
);

-- 인덱스
create index idx_candidates_room   on candidates(room_id);
create index idx_votes_room        on votes(room_id);
create index idx_spins_room        on spins(room_id);
create index idx_rooms_expires     on rooms(expires_at);
create index idx_place_cache_time  on place_cache(fetched_at);
```

### 6.2 득표 집계 — 경쟁 상태를 구조적으로 제거

v1.0은 `vote_count INT`를 두어 read-modify-write 경쟁 상태가 발생하는 구조였습니다. v2.0은 **카운터 컬럼을 두지 않습니다.**

```sql
create view v_vote_tally as
select c.room_id, c.id as candidate_id, c.name, count(v.id) as votes
from candidates c
left join votes v on v.candidate_id = c.id
group by c.room_id, c.id, c.name;
```

- 방 인원은 최대 수십 명이므로 매 조회 집계 비용이 무시할 수준입니다.
- 클라이언트는 `votes` 테이블 변경을 Realtime으로 구독하여 **자체 집계**합니다 → 서버 왕복 없이 즉시 반영, 경쟁 상태 원천 부재.
- 투표 변경은 `insert ... on conflict (room_id, participant_id) do update` 단일 원자 연산으로 처리합니다.

### 6.3 타이머 — 백그라운드 워커 없이 처리

별도 스케줄러(cron/worker)를 두지 않습니다. `rooms.timer_ends_at`을 서버 권위 시각으로 두고, **읽기 시점에 지연 마감(lazy close)** 합니다.

```sql
create or replace function close_room_if_due(p_room_id uuid)
returns rooms language plpgsql security definer as $$
declare r rooms;
begin
  update rooms set status = 'closed',
         winner_candidate_id = coalesce(winner_candidate_id, (
           select candidate_id from v_vote_tally
           where room_id = p_room_id
           order by votes desc, md5(candidate_id::text || p_room_id::text)  -- 동점 시 결정론적 무작위
           limit 1))
  where id = p_room_id and status = 'voting' and timer_ends_at <= now()
  returning * into r;

  if r.id is null then select * into r from rooms where id = p_room_id; end if;
  return r;
end $$;
```

동점 시 `md5(...)` 정렬은 **결정론적이면서 예측 불가능**하므로, 여러 클라이언트가 동시에 마감을 트리거해도 동일한 승자가 나옵니다.

### 6.4 RLS 정책 — 쓰기 전면 차단

```sql
alter table rooms        enable row level security;
alter table participants enable row level security;
alter table candidates   enable row level security;
alter table votes        enable row level security;
alter table spins        enable row level security;
alter table place_cache  enable row level security;

-- 기본: 모든 테이블에 anon 정책 없음 = 전면 거부
-- 모든 INSERT/UPDATE/DELETE는 서버(Server Action, service_role)를 통해서만 수행

-- Realtime 구독에 필요한 최소 SELECT만 개방
create policy realtime_read_votes      on votes      for select to anon using (true);
create policy realtime_read_candidates on candidates for select to anon using (true);
```

**설계 근거와 잔여 리스크 (숨기지 않음):** Supabase Realtime의 Postgres Changes는 구독 대상에 대한 SELECT 권한을 요구합니다. 위 정책은 anon 키 보유자가 `candidates` 전체(식당명·좌표)를 열람할 수 있음을 의미합니다.

- **허용 가능한 이유:** 해당 테이블에는 개인정보가 전혀 없습니다(공개된 상점 정보뿐). 개인 식별 요소인 `nickname`은 `participants`에 있고 이 테이블은 anon 전면 거부입니다. 방 접근의 실질 비밀은 `rooms.code`(nanoid 10자)이며 `rooms` 역시 anon 거부입니다.
- **업그레이드 경로(v1.1):** Postgres Changes → **Realtime Broadcast 사설 채널**로 전환하여 서버가 방별 채널에만 집계를 브로드캐스트. 그 시점에 위 두 SELECT 정책을 제거합니다.

### 6.5 데이터 수명 주기

```sql
create or replace function purge_expired_rooms()
returns void language sql security definer as $$
  delete from rooms where expires_at < now();   -- cascade로 하위 전부 정리
$$;
```

Supabase `pg_cron`으로 1시간 주기 실행. **방은 생성 24시간 후 전량 삭제**됩니다. 이는 저장소 관리인 동시에 개인정보 최소 보관 원칙의 이행이기도 합니다(§9).

---

## 7. 비용 모델 (v1.0 완전 누락분)

### 7.1 v0 운영비

| 항목 | 플랜 | 월 비용 | 한계선 |
|---|---|---|---|
| Vercel | Hobby | **0원** | 상업적 이용 시 Pro($20) 필요 — 수익화 시점에 전환 |
| Supabase | Free | **0원** | DB 500MB / MAU 5만. 24시간 삭제 정책으로 용량은 사실상 무제한 |
| 카카오 로컬 API | 무료 쿼터 | **0원** | 일일 쿼터 (착수 시 실측 확인 필요) |
| 도메인 | 미사용 (`*.vercel.app`) | **0원** | 검증 후 구매 |
| **합계** | | **월 0원** | |

**v0는 금전 비용 0원으로 운영 가능합니다.** 이것이 Google Places 대신 카카오를 택한 두 번째 이유입니다.

### 7.2 API 호출량 추정

캐싱 설계(§3.3) 하에서:

```
일일 카카오 API 호출 ≈ 일일 방 생성 수 × 캐시 미스율 × 2콜

예) 일 1,000개 방, 캐시 미스율 20%(오피스 밀집 지역 반복 사용 가정)
    = 1,000 × 0.2 × 2 = 400콜/일
```

리롤·참가자 수와 무관하므로, 일 1,000개 방(= 대략 DAU 4,000~8,000명) 규모까지 무료 쿼터 안에서 처리 가능할 것으로 추정합니다.

**대조 — v1.0 설계의 경우:** 리롤 1회 = Nearby Search 1콜 + Details N콜. 유저 1인당 평균 3회 리롤, 후보 8곳 상세 조회 시 유저 1명당 약 25~30콜. DAU 1,000명이면 **일 3만 콜**. Google Places 유료 SKU 기준으로 월 수백 달러 이상이 발생하며, 이는 수익 0원 단계에서 감당 불가한 구조였습니다.

> ⚠️ 위 Google 측 금액은 공개 요금표 기준의 개략 추정입니다. v1.1에서 Google 연동을 검토할 때는 반드시 당시 공식 요금표를 재확인하십시오.

### 7.3 손익 관점

**v0 목표 수익은 0원입니다.** v1.0이 제시한 수익모델 3종은 모두 트래픽 선행이 전제입니다.

| 수익원 | 실행 가능 조건 | 판정 |
|---|---|---|
| 스폰서드 룰렛 | 지역 상권 광고주가 구매할 만한 지역별 트래픽. 최소 MAU 수만 | 이연 |
| 예약 플랫폼 제휴 | 캐치테이블·테이블링 등은 개인/초기 서비스에 제휴 프로그램을 개방하지 않는 것이 일반적. 사업자 등록 + 트래픽 증빙 필요 | 이연 |
| B2B 팀 SaaS | 별개 제품 + 영업 조직 필요 | 이연 |

가장 현실적인 최초 수익 경로는 **① 검증 성공 → ② 트래픽 확보 → ③ 지역 상권 광고**이며, 최소 6~12개월 이후 논의 대상입니다. **v0 단계에서 수익 계획을 세우는 것은 계획이 아니라 희망입니다.**

---

## 8. 검증 지표 및 중단 기준

v0는 기능 완성이 아니라 **가설 판정**이 목적이므로, 성공/실패 기준을 착수 전에 고정합니다.

### 8.1 측정 지표

| # | 지표 | 정의 | 성공선 | 실패선 |
|---|---|---|---|---|
| **M1** | 방당 참여자 수 | 방 1개의 참가자 수 중앙값 | **≥ 3명** | < 2명 |
| **M2** | 투표 완료율 | 생성된 방 중 승자 확정까지 도달한 비율 | **≥ 50%** | < 25% |
| **M3** | 호스트 7일 재사용률 | 방 생성자가 7일 내 방을 다시 만든 비율 | **≥ 20%** | < 5% |
| M4 | 링크 클릭 전환율 | 공유 링크 방문자 중 참가 완료 비율 | ≥ 60% | — |

*M1~M3가 1차 판정 기준입니다. 측정 기간: 공개 후 3주, 최소 방 200개.*

### 8.2 판정

- **M1·M2·M3 모두 성공선 이상** → 가설 참. §10 로드맵 진행.
- **M1만 성공, M3 실패** → "같이 쓰긴 하는데 다시 안 온다". 제품이 아니라 습관 형성의 문제. → 재방문 훅(PWA/알림/봇 연동) 우선 재설계.
- **M1 실패** (혼자만 씀) → 핵심 가설 거짓. **더 만들지 말고 중단.** 협업이 아니라 개인용 도구로 전면 재정의하거나 프로젝트를 종료합니다.
- **어느 지표든 실패선 이하** → 기능 추가로 만회하려는 시도를 금지합니다. v1.0이 실패한 방식(검증 없이 기능만 쌓기)의 반복입니다.

### 8.3 계측 구현

- Vercel Analytics + 자체 이벤트 테이블(`room_created`, `participant_joined`, `spin_done`, `vote_cast`, `room_closed`)
- 호스트 식별은 localStorage 익명 ID (개인정보 아님, 재사용률 측정 전용)

---

## 9. 법적·개인정보 검토 (v1.0 완전 누락분)

무로그인이라 해도 **위치 정보를 다루는 순간 국내 법적 검토 대상**이 됩니다. v1.0에는 이 항목이 전혀 없었습니다.

| 항목 | v0 대응 |
|---|---|
| 위치정보법 (위치정보의 보호 및 이용 등에 관한 법률) | 개인위치정보 처리 여부에 따라 사업자 신고 의무가 발생할 수 있음. **v0는 좌표를 소수점 3자리(약 110m 격자)로 반올림하여 저장하고, 개인 단말과 좌표를 연결하는 식별자를 저장하지 않음.** 그럼에도 서비스 공개 전 법률 검토를 받을 것 — 이 표는 검토 대체물이 아님 |
| 개인정보 수집 | 이름·이메일·전화번호 등 일절 수집하지 않음. 닉네임은 선택 입력이며 24시간 후 삭제 |
| 보관 기간 | 모든 방 데이터 **24시간 후 자동 완전 삭제** (§6.5) |
| 필수 문서 | 이용약관, 개인정보처리방침, 위치기반서비스 이용약관 — **공개 전 필수 게시** |
| 브라우저 위치 권한 | 권한 요청 전 목적 고지 화면 선행 표시 |
| 외부 API 약관 | 카카오 로컬 API 및 카카오맵 딥링크의 상업적 이용 조건, 저작권 표기 의무 확인 |

---

## 10. 실행 계획

### 10.1 v0 — 2주 (실작업 10일 기준)

| Day | 작업 | 완료 정의 |
|---|---|---|
| 1 | **카카오 API 스펙·쿼터·약관 실측 확인**, 응답 필드 검증 | 실제 응답 JSON 확보. 여기서 막히면 **즉시 전체 계획 재검토** |
| 1–2 | Next.js + Supabase + Vercel 초기화, DDL 적용, RLS 정책 | 빈 앱 배포 성공 |
| 2–3 | 위치 획득(GPS + 주소 검색 폴백), 후보 조회 + `place_cache` | 좌표 입력 → 후보 45곳 반환 |
| 3–5 | 룰렛 컴포넌트 (Framer Motion), 혼자 뽑기 전체 플로우 | 혼자 뽑기 모드 E2E 동작 |
| 5–7 | 방 생성/참가, 익명 토큰, 각자 스핀 → Top 3 집계 | 2개 브라우저로 방 동시 참가 확인 |
| 7–9 | 실시간 투표, 1인 1표, 타이머, 승자 확정, Confetti | 5개 세션 동시 투표 정상 동작 |
| 9–10 | OG 이미지, 카카오톡 공유, 결과 화면, 약관/방침 페이지, 계측 | 카톡 공유 → 링크 클릭 → 참가 전체 경로 검증 |

**버퍼 없음이 아니라, 버퍼가 필요하면 기능을 더 쳐냅니다.** 일정이 밀리면 우선 삭제 순서: ① OG 동적 이미지(정적 이미지로 대체) ② Confetti ③ 주소 검색 폴백(GPS 전용).

### 10.2 게이트

```
v0 완성 ──► 3주 측정 ──► [게이트 A: M1·M2·M3 판정]
                              │
              성공 ───────────┤─────────── 실패 ──► 중단 또는 가설 재정의
                              ▼
                        v1.0 (4주): 재방문 강화 — PWA 홈 추가, "내일도 이 팀으로",
                                    최근 방문 제외 추천, 닉네임/프로필
                              │
                              ▼
                       [게이트 B: MAU 1만 · M3 ≥ 30%]
                              │
                              ▼
                        v1.1 (4주): 승자 1곳 한정 Google 평점 보강,
                                    카카오맵 길찾기 심화, 디저트 카페 연계
                              │
                              ▼
                       [게이트 C: MAU 5만]
                              │
                              ▼
                        v2.0: 로그인 + 방문 기록 아카이브, 수익화 착수
```

각 게이트를 통과하지 못하면 **다음 단계를 시작하지 않습니다.** v1.0 문서의 가장 큰 구조적 오류는 게이트 없이 4개 Phase를 일직선으로 배치한 것이었습니다.

---

## 11. 리스크 등록부

| # | 리스크 | 영향 | 대응 |
|---|---|---|---|
| R1 | 카카오 API 쿼터/약관이 상업적 이용을 제한 | **치명** | Day 1에 최우선 확인. 불가 시 네이버 지역검색 API 대안 검토 후 재기획 |
| R2 | 평점 미표시로 추천 신뢰도 하락 | 중 | 카카오맵 딥링크로 위임. M2(투표 완료율)로 조기 감지 |
| R3 | 모방 용이 — 경쟁사 2주면 추격 | 중 | 속도 우선. 검증 전 홍보 확대 자제 |
| R4 | 재방문 훅 부재 (무로그인 구조의 한계) | **높음** | M3로 직접 측정. 실패 시 게이트 A에서 재설계 결정 |
| R5 | 위치정보 관련 법적 요구사항 | 높음 | 좌표 반올림 + 24시간 삭제 + 공개 전 법률 검토 |
| R6 | Realtime SELECT 개방으로 인한 후보 데이터 노출 | 낮음 | 개인정보 미포함. v1.1에서 Broadcast 사설 채널로 전환 |
| R7 | 도보 거리 = 직선거리 근사 | 낮음 | "약" 표기. 정확 도보 시간은 카카오맵 길찾기에 위임 |

---

## 12. AI 개발 도구 활용 가이드 (수정판)

v1.0의 프롬프트는 삭제된 기능(혼잡도 등)을 전제하고 있어 전면 교체합니다.

**아키텍처·서버 로직**
> "Next.js 15 App Router + Supabase에서, 무로그인 익명 토큰으로 참가자를 식별하고 `UNIQUE(room_id, participant_id)` 제약으로 1인 1표를 보장하는 투표 Server Action을 작성해줘. 투표 변경은 `on conflict do update`로 원자적으로 처리하고, 모든 쓰기는 service_role 클라이언트로 서버에서만 수행해야 해. 득표수는 카운터 컬럼 없이 votes 행 집계로 계산해."

**프론트엔드**
> "Tailwind + Framer Motion으로 8칸 룰렛 컴포넌트를 만들어줘. 고정된 후보 배열을 props로 받아 클라이언트에서만 셔플/회전하고(네트워크 호출 없음), 회전 종료 시 당첨 인덱스를 콜백으로 넘겨줘. 모바일 세로 화면 우선."

**검토·보안**
> "이 Supabase RLS 정책에서 anon 키를 가진 공격자가 접근 가능한 데이터 범위를 정리하고, 방 코드(nanoid 10자)만 아는 사람과 모르는 사람이 각각 무엇을 할 수 있는지 표로 정리해줘. 개인정보가 노출되는 경로가 있으면 지적해줘."

**주의:** 어떤 AI 도구든 **외부 API가 실제로 제공하는 필드**를 지어내는 경향이 있습니다. v1.0의 "Google Places 혼잡도"가 정확히 그 사례입니다. **API 관련 사항은 반드시 공식 문서 원문과 실제 응답 JSON으로 검증하십시오.**

---

## 13. 미결 사항 (착수 전 결정 필요)

1. **카카오 로컬 API 상업적 이용 조건** — Day 1 확인. 결과에 따라 §3 전체가 바뀔 수 있음
2. **사업자 등록 여부** — 위치기반서비스 신고 및 향후 수익화의 전제
3. **v0 공개 범위** — 지인 팀 5~10곳 비공개 테스트 후 공개 vs 즉시 공개
4. **저장소** — 본 문서는 현재 `DCP_AGA`(탈모 신약개발 데이터 파이프라인) 저장소에 임시 보관 중이며, **구현은 반드시 별도 저장소에서 진행**해야 합니다

---

## 부록 A. v1.0 대비 범위 축소 요약

```
v1.0:  화면 5개 · 게임 4종 · 테마 5개 · 외부 API 4개 · 인프라 4종 · 기능 약 30개
v2.0:  화면 4개 · 게임 1종 · 테마 0개 · 외부 API 1개 · 인프라 2종 · 기능 약 10개

삭제된 기능 대부분은 "만들 수 없는 것"이었고,
남은 기능 전부는 "2주 안에 만들 수 있고 가설을 판정할 수 있는 것"입니다.
```

## 부록 B. 문서 이력

| 버전 | 일자 | 변경 |
|---|---|---|
| v1.0.0 | 2026-08-18 | 최초 작성. 구현 불가 항목 다수 포함으로 폐기 |
| v2.0.0 | 2026-08-18 | 전면 재작성. 데이터 소스 교체, 범위 축소, 비용/법적/검증 지표 신규 추가 |
