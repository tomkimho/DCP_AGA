"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Confetti from "@/components/Confetti";
import Roulette from "@/components/games/Roulette";
import SlotMachine from "@/components/games/SlotMachine";
import Revolver from "@/components/games/Revolver";
import CardFlip from "@/components/games/CardFlip";
import MapView from "@/components/map/MapView";
import { COLORS, GAMES, gameById, type GameId } from "@/lib/games";
import { walkMinutes } from "@/lib/grid";
import * as sound from "@/lib/sound";
import type { Coords, Place, PlacesResponse } from "@/lib/types";

type Step = "location" | "play" | "result";
type LocState = "locating" | "ok" | "denied" | "unsupported" | "manual";

const RADIUS_OPTIONS = [
  { m: 400, label: "도보 5분" },
  { m: 800, label: "도보 10분" },
  { m: 1200, label: "도보 15분" },
];

/** 위치를 못 잡았을 때 지도를 띄워 둘 임시 중심 */
const FALLBACK_CENTER: Coords = { lat: 37.5665, lng: 126.978 };

const PRESETS: Array<{ name: string; coords: Coords }> = [
  { name: "강남역", coords: { lat: 37.4979, lng: 127.0276 } },
  { name: "여의도역", coords: { lat: 37.5215, lng: 126.9243 } },
  { name: "판교역", coords: { lat: 37.3947, lng: 127.1112 } },
  { name: "시청역", coords: { lat: 37.5657, lng: 126.977 } },
  { name: "홍대입구역", coords: { lat: 37.5572, lng: 126.9245 } },
  { name: "잠실역", coords: { lat: 37.5133, lng: 127.1 } },
];

function shuffle<T>(arr: T[]): T[] {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

function mealLabel(): string {
  const h = new Date().getHours();
  return h >= 11 && h < 15 ? "점심" : h >= 15 && h < 22 ? "저녁" : "한 끼";
}

export default function Page() {
  const [step, setStep] = useState<Step>("location");
  const [radiusM, setRadiusM] = useState(800);

  const [center, setCenter] = useState<Coords | null>(null);
  const [userAt, setUserAt] = useState<Coords | null>(null);
  const [locState, setLocState] = useState<LocState>("locating");
  const [placeLabel, setPlaceLabel] = useState("이 근처");

  const [preview, setPreview] = useState<Place[]>([]);
  const [pool, setPool] = useState<Place[]>([]);
  const [demo, setDemo] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [gameId, setGameId] = useState<GameId>("roulette");
  const [slots, setSlots] = useState<Place[]>([]);
  const [round, setRound] = useState(0);
  const [running, setRunning] = useState(false);
  const [winner, setWinner] = useState<Place | null>(null);
  const [confettiKey, setConfettiKey] = useState(0);
  const [copied, setCopied] = useState(false);
  const [muted, setMuted] = useState(false);

  const meal = useMemo(() => mealLabel(), []);
  const game = gameById(gameId);
  const apiCalls = useRef(0);
  const revealTimer = useRef<number | null>(null);

  const clearReveal = useCallback(() => {
    if (revealTimer.current !== null) {
      clearTimeout(revealTimer.current);
      revealTimer.current = null;
    }
  }, []);

  useEffect(() => clearReveal, [clearReveal]);

  useEffect(() => {
    sound.loadMutePref();
    setMuted(sound.isMuted());
    return sound.onMuteChange(setMuted);
  }, []);

  /* ── 시작하자마자 내 위치를 잡는다 ── */
  useEffect(() => {
    if (!("geolocation" in navigator)) {
      setLocState("unsupported");
      setCenter(FALLBACK_CENTER);
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const c = { lat: pos.coords.latitude, lng: pos.coords.longitude };
        setUserAt(c);
        setCenter(c);
        setLocState("ok");
        setPlaceLabel("현재 위치");
      },
      () => {
        setLocState("denied");
        setCenter(FALLBACK_CENTER);
      },
      { enableHighAccuracy: false, timeout: 10_000, maximumAge: 300_000 }
    );
  }, []);

  const fetchPlaces = useCallback(async (c: Coords, r: number) => {
    const res = await fetch(`/api/places?lat=${c.lat}&lng=${c.lng}&radius=${r}`);
    if (!res.ok) throw new Error(`요청 실패 (${res.status})`);
    const data: PlacesResponse = await res.json();
    if (!data.cached) apiCalls.current += 1;
    setDemo(data.demo);
    return data.places;
  }, []);

  /*
   * 지도를 움직이는 동안 매 프레임 조회하면 실제 배포본에서 카카오 호출이
   * 폭증한다. 손을 뗀 뒤에만 한 번 조회한다.
   */
  useEffect(() => {
    if (step !== "location" || !center) return;
    let dead = false;
    setLoading(true);
    const t = window.setTimeout(() => {
      fetchPlaces(center, radiusM)
        .then((places) => {
          if (dead) return;
          setPreview(places);
          setError(null);
        })
        .catch((e: Error) => {
          if (!dead) setError(e.message);
        })
        .finally(() => {
          if (!dead) setLoading(false);
        });
    }, 400);
    return () => {
      dead = true;
      clearTimeout(t);
    };
  }, [step, center, radiusM, fetchPlaces]);

  const dealSlots = useCallback((from: Place[], count: number) => {
    setSlots(shuffle(from).slice(0, Math.min(count, from.length)));
    setRound((r) => r + 1);
  }, []);

  const start = useCallback(() => {
    if (preview.length < 3) return;
    sound.unlock();
    sound.blip();
    setPool(preview);
    setWinner(null);
    dealSlots(preview, game.slots);
    setStep("play");
  }, [preview, game.slots, dealSlots]);

  const usePreset = useCallback((p: { name: string; coords: Coords }) => {
    sound.unlock();
    sound.blip();
    setUserAt(null);
    setLocState("manual");
    setCenter(p.coords);
    setPlaceLabel(p.name);
  }, []);

  const recenter = useCallback(() => {
    if (!userAt) return;
    sound.blip();
    setCenter(userAt);
  }, [userAt]);

  /**
   * 게임이 결과를 확정한 순간 바로 결과 화면으로 넘기면
   * 슬롯의 777이 맞춰지는 장면이나 룰렛이 멈춘 자리를 볼 수 없다.
   * 축하 효과는 즉시 터뜨리고, 화면 전환만 잠깐 미룬다.
   */
  const onResult = useCallback(
    (index: number) => {
      const picked = slots[index];
      if (!picked) return;
      setWinner(picked);
      setConfettiKey((k) => k + 1);
      sound.fanfare();

      clearReveal();
      revealTimer.current = window.setTimeout(() => {
        revealTimer.current = null;
        setStep("result");
      }, 1100);
    },
    [slots, clearReveal]
  );

  /** 같은 후보 풀 안에서 판을 다시 짠다 — 외부 API 호출이 발생하지 않는다 */
  const playAgain = useCallback(() => {
    sound.unlock();
    sound.blip();
    clearReveal();
    setWinner(null);
    dealSlots(pool, game.slots);
    setStep("play");
  }, [pool, game.slots, dealSlots, clearReveal]);

  const switchGame = useCallback(
    (id: GameId) => {
      if (running || id === gameId) return;
      sound.unlock();
      sound.blip();
      clearReveal();
      setGameId(id);
      setWinner(null);
      dealSlots(pool, gameById(id).slots);
      setStep("play");
    },
    [running, gameId, pool, dealSlots, clearReveal]
  );

  const share = useCallback(async () => {
    if (!winner) return;
    const text = `오늘 ${meal}은 「${winner.name}」! 🍽️`;
    try {
      if (navigator.share) {
        await navigator.share({ title: "Random Plate", text, url: location.href });
        return;
      }
      await navigator.clipboard.writeText(`${text}\n${location.href}`);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* 사용자가 공유 시트를 닫은 경우 — 무시 */
    }
  }, [winner, meal]);

  useEffect(() => {
    setCopied(false);
  }, [winner]);

  /**
   * 컴포넌트 함수로 만들면 Page가 리렌더될 때마다 새 타입이 되어 게임이
   * 통째로 리마운트된다(회전 중 상태가 날아간다). 엘리먼트를 반환하는
   * 평범한 함수여야 React가 SlotMachine/Roulette 같은 실제 타입으로 재조정한다.
   */
  const renderGame = () => {
    const props = { slots, onResult, onRunningChange: setRunning };
    switch (gameId) {
      case "slot":
        return <SlotMachine {...props} />;
      case "revolver":
        return <Revolver {...props} />;
      case "cards":
        return <CardFlip {...props} />;
      default:
        return <Roulette {...props} />;
    }
  };

  const locLine =
    locState === "locating"
      ? "위치 확인 중…"
      : locState === "ok"
        ? "현재 위치"
        : locState === "manual"
          ? placeLabel
          : "위치를 쓸 수 없어요 — 아래에서 골라주세요";

  return (
    <main className="mx-auto w-full max-w-md px-5 pb-12 pt-6 lg:max-w-5xl lg:px-8 lg:pt-10">
      <Confetti fire={confettiKey} />

      <header className="mb-6 flex items-start justify-between gap-4 lg:mb-9">
        <div>
          <h1 className="text-2xl font-black tracking-tight lg:text-3xl">
            Random&nbsp;Plate
            <span className="ml-2 align-middle text-[11px] font-bold text-white/40">
              v0
            </span>
          </h1>
          <p className="mt-1 text-sm text-white/55">
            오늘 {meal} 뭐 먹지? 한 판이면 끝.
          </p>
        </div>

        <button
          onClick={() => {
            sound.unlock();
            if (!sound.toggleMute()) sound.blip();
          }}
          className="shrink-0 rounded-full border border-white/15 bg-white/5 px-3 py-2 text-sm transition hover:bg-white/10"
          aria-label={muted ? "효과음 켜기" : "효과음 끄기"}
          title={muted ? "효과음 켜기" : "효과음 끄기"}
        >
          {muted ? "🔇" : "🔊"}
        </button>
      </header>

      {error && (
        <div className="mb-4 rounded-xl border border-red-400/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">
          {error}
        </div>
      )}

      {step === "location" && (
        <section className="pop-in mx-auto flex max-w-2xl flex-col gap-5">
          <div className="relative h-[46vh] max-h-[26rem] w-full overflow-hidden rounded-2xl border border-white/10 bg-[#0a0710] lg:h-[24rem] lg:max-h-none">
            {center && (
              <MapView
                center={center}
                radiusM={radiusM}
                places={preview}
                userAt={userAt}
                interactive
                onCenterChange={setCenter}
                className="h-full w-full"
              />
            )}

            <div className="pointer-events-none absolute left-3 top-3 flex items-center gap-2 rounded-full border border-white/15 bg-black/70 px-3 py-1.5 text-xs font-bold backdrop-blur">
              <span
                className={`h-2 w-2 rounded-full ${
                  locState === "ok"
                    ? "bg-emerald-400"
                    : locState === "denied" || locState === "unsupported"
                      ? "bg-red-400"
                      : "bg-white/40"
                }`}
              />
              {locLine}
            </div>

            {userAt && (
              <button
                onClick={recenter}
                className="absolute bottom-3 right-3 grid h-10 w-10 place-items-center rounded-full border border-white/15 bg-black/70 text-sm backdrop-blur transition hover:border-amber-300"
                aria-label="내 위치로"
                title="내 위치로"
              >
                ◎
              </button>
            )}
          </div>

          <div>
            <p className="mb-3 text-sm font-semibold text-white/80">
              얼마나 걸어갈 수 있나요?
            </p>
            <div className="grid grid-cols-3 gap-2">
              {RADIUS_OPTIONS.map((o) => (
                <button
                  key={o.m}
                  onClick={() => {
                    sound.blip();
                    setRadiusM(o.m);
                  }}
                  className={`rounded-xl border px-3 py-3 text-sm font-bold transition ${
                    radiusM === o.m
                      ? "border-white/70 bg-white text-black"
                      : "border-white/15 bg-white/5 text-white/75 hover:bg-white/10"
                  }`}
                >
                  {o.label}
                  <span className="block text-[11px] font-medium opacity-60">
                    {o.m}m
                  </span>
                </button>
              ))}
            </div>
          </div>

          <button
            onClick={start}
            disabled={loading || preview.length < 3}
            className="rounded-2xl bg-gradient-to-r from-indigo-500 to-fuchsia-500 px-5 py-4 text-base font-black shadow-lg shadow-fuchsia-900/30 transition active:scale-[0.98] disabled:opacity-50"
          >
            {loading ? "주변을 찾는 중…" : "이 근처에서 시작"}
          </button>

          <p className="text-center text-[11px] leading-relaxed text-white/40">
            {loading
              ? " "
              : preview.length >= 3
                ? `반경 안에 ${preview.length}곳 · 지도를 끌어서 중심을 옮길 수 있습니다.`
                : "이 근처엔 후보가 부족합니다. 반경을 넓히거나 지도를 옮겨 보세요."}
          </p>

          <details className="border-t border-white/10 pt-4">
            <summary className="cursor-pointer text-sm font-semibold text-white/60 hover:text-white/85">
              위치를 직접 고르기
            </summary>
            <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
              {PRESETS.map((p) => (
                <button
                  key={p.name}
                  onClick={() => usePreset(p)}
                  className="card rounded-xl px-3 py-3 text-sm font-semibold text-white/85 transition hover:bg-white/10"
                >
                  {p.name}
                </button>
              ))}
            </div>
          </details>
        </section>
      )}

      {(step === "play" || step === "result") && (
        <div className="lg:grid lg:grid-cols-[minmax(0,1fr)_340px] lg:items-start lg:gap-12">
          <section className="flex flex-col gap-5">
            <div className="flex flex-wrap gap-2">
              {GAMES.map((g) => (
                <button
                  key={g.id}
                  onClick={() => switchGame(g.id)}
                  disabled={running}
                  className={`rounded-full border px-3 py-1.5 text-xs font-bold transition disabled:opacity-40 ${
                    g.id === gameId
                      ? "border-white/70 bg-white text-black"
                      : "border-white/15 bg-white/5 text-white/70 hover:bg-white/10"
                  }`}
                >
                  {g.emoji} {g.name}
                </button>
              ))}
            </div>

            {step === "play" ? (
              <div
                key={`${gameId}-${round}`}
                className="pop-in flex w-full lg:min-h-[540px] lg:items-center"
              >
                {renderGame()}
              </div>
            ) : (
              winner && (
                <div className="pop-in flex flex-col gap-4">
                  <div className="card rounded-2xl px-5 py-6 lg:px-7 lg:py-8">
                    <p className="text-xs font-bold tracking-wide text-fuchsia-300">
                      오늘의 {meal} · {game.emoji} {game.name}
                    </p>
                    <h2 className="mt-1 text-2xl font-black leading-tight lg:text-4xl">
                      {winner.name}
                    </h2>
                    <p className="mt-2 text-sm text-white/60">
                      {winner.category} · 약 {winner.distanceM}m (도보{" "}
                      {walkMinutes(winner.distanceM)}분)
                    </p>
                    {winner.roadAddress && (
                      <p className="mt-1 text-xs text-white/40">
                        {winner.roadAddress}
                      </p>
                    )}
                  </div>

                  <button onClick={playAgain} className="btn-primary">
                    🔄 다시 하기
                  </button>

                  <a
                    href={winner.placeUrl}
                    target="_blank"
                    rel="noreferrer noopener"
                    className="rounded-2xl bg-[#ffe812] px-5 py-4 text-center text-base font-black text-black transition active:scale-[0.98]"
                  >
                    지도에서 보기
                  </a>

                  <button onClick={share} className="btn-ghost">
                    {copied ? "복사됨!" : "공유하기"}
                  </button>
                </div>
              )
            )}
          </section>

          <aside className="mt-8 flex flex-col gap-4 lg:mt-0">
            <div className="flex items-center justify-between text-xs text-white/50">
              <span>
                {placeLabel} · 반경 {radiusM}m · 후보 {pool.length}곳
              </span>
              <button
                onClick={() => {
                  clearReveal();
                  setStep("location");
                  setWinner(null);
                }}
                disabled={running}
                className="underline underline-offset-2 hover:text-white/80 disabled:opacity-40"
              >
                위치 변경
              </button>
            </div>

            {center && (
              <div className="relative aspect-square w-full overflow-hidden rounded-2xl border border-white/10 bg-[#0a0710]">
                <MapView
                  center={center}
                  radiusM={radiusM}
                  places={pool}
                  slots={slots}
                  winner={winner}
                  userAt={userAt}
                  className="h-full w-full"
                />
              </div>
            )}

            <div className="card rounded-2xl p-4">
              <p className="mb-3 text-xs font-bold text-white/60">
                이번 판 후보 {slots.length}곳
              </p>
              <ol className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-1">
                {slots.map((p, i) => {
                  const isWinner = winner?.id === p.id;
                  return (
                    <li
                      key={p.id}
                      data-slot={i}
                      className={`flex items-center gap-2 overflow-hidden rounded-lg px-1.5 py-1 transition ${
                        isWinner ? "bg-white/10" : ""
                      }`}
                    >
                      <span
                        className="grid h-5 w-5 shrink-0 place-items-center rounded-md text-[11px] font-black text-black"
                        style={{ background: COLORS[i % COLORS.length] }}
                      >
                        {i + 1}
                      </span>
                      <span
                        className={`truncate text-[13px] font-semibold ${
                          isWinner ? "text-white" : "text-white/75"
                        }`}
                      >
                        {p.name}
                      </span>
                      <span className="ml-auto shrink-0 text-[11px] text-white/35">
                        {p.distanceM}m
                      </span>
                    </li>
                  );
                })}
              </ol>
            </div>

            <button onClick={playAgain} disabled={running} className="btn-ghost">
              후보 {game.slots}곳 다시 뽑기
            </button>

            <p className="text-center text-[11px] leading-relaxed text-white/35">
              이번 세션 외부 API 호출{" "}
              <b className="text-white/60">{apiCalls.current}회</b>
              <br />
              (후보 풀을 고정해 두므로 몇 번을 다시 해도 호출이 늘지 않습니다)
            </p>
          </aside>
        </div>
      )}

      <footer className="mt-12 text-center text-[11px] leading-relaxed text-white/30">
        {demo ? (
          <span className="inline-block rounded-full border border-amber-300/30 bg-amber-400/10 px-3 py-1 font-bold text-amber-200">
            데모 데이터 — 실제 식당이 아닙니다
          </span>
        ) : (
          <span>장소 데이터: 카카오 로컬 API</span>
        )}
        <p className="mt-3">
          Stage 1 · 혼자 뽑기 전용. 팀 투표는 Stage 2에서 붙습니다.
        </p>
      </footer>
    </main>
  );
}
