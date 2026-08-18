"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Confetti from "@/components/Confetti";
import Roulette, { COLORS } from "@/components/games/Roulette";
import SlotMachine from "@/components/games/SlotMachine";
import Revolver from "@/components/games/Revolver";
import CardFlip from "@/components/games/CardFlip";
import { GAMES, gameById, type GameId } from "@/lib/games";
import { walkMinutes } from "@/lib/grid";
import * as sound from "@/lib/sound";
import type { Coords, Place, PlacesResponse } from "@/lib/types";

type Step = "location" | "play" | "result";

const RADIUS_OPTIONS = [
  { m: 400, label: "도보 5분" },
  { m: 800, label: "도보 10분" },
  { m: 1200, label: "도보 15분" },
];

/** GPS 거부 시의 폴백. 주소 검색은 카카오 키가 필요하므로 Stage 2로 미뤘다. */
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
  const [placeLabel, setPlaceLabel] = useState<string | null>(null);

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

  const dealSlots = useCallback((from: Place[], count: number) => {
    setSlots(shuffle(from).slice(0, Math.min(count, from.length)));
    setRound((r) => r + 1);
  }, []);

  const loadPlaces = useCallback(
    async (coords: Coords, label: string, radius: number) => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(
          `/api/places?lat=${coords.lat}&lng=${coords.lng}&radius=${radius}`
        );
        if (!res.ok) throw new Error(`요청 실패 (${res.status})`);
        const data: PlacesResponse = await res.json();

        if (!data.cached) apiCalls.current += 1;

        if (data.places.length === 0) {
          setError(
            "이 반경 안에서 식당을 찾지 못했습니다. 반경을 넓혀서 다시 시도해 주세요."
          );
          return;
        }

        setPool(data.places);
        setDemo(data.demo);
        setPlaceLabel(label);
        setWinner(null);
        dealSlots(data.places, gameById(gameId).slots);
        setStep("play");
      } catch (e) {
        setError(e instanceof Error ? e.message : "알 수 없는 오류");
      } finally {
        setLoading(false);
      }
    },
    [dealSlots, gameId]
  );

  const useGps = useCallback(() => {
    sound.unlock();
    if (!("geolocation" in navigator)) {
      setError("이 브라우저는 위치 기능을 지원하지 않습니다. 아래에서 골라주세요.");
      return;
    }
    setLoading(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        void loadPlaces(
          { lat: pos.coords.latitude, lng: pos.coords.longitude },
          "현재 위치",
          radiusM
        );
      },
      () => {
        setLoading(false);
        setError("위치 권한이 거부됐습니다. 아래에서 직접 골라주세요.");
      },
      { enableHighAccuracy: false, timeout: 10_000, maximumAge: 300_000 }
    );
  }, [loadPlaces, radiusM]);

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
    const props = {
      slots,
      onResult,
      onRunningChange: setRunning,
    };
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
            const next = sound.toggleMute();
            if (!next) sound.blip();
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
        <section className="pop-in mx-auto flex max-w-md flex-col gap-6">
          <div>
            <p className="mb-3 text-sm font-semibold text-white/80">
              얼마나 걸어갈 수 있나요?
            </p>
            <div className="grid grid-cols-3 gap-2">
              {RADIUS_OPTIONS.map((o) => (
                <button
                  key={o.m}
                  onClick={() => setRadiusM(o.m)}
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
            onClick={useGps}
            disabled={loading}
            className="rounded-2xl bg-gradient-to-r from-indigo-500 to-fuchsia-500 px-5 py-4 text-base font-black shadow-lg shadow-fuchsia-900/30 transition active:scale-[0.98] disabled:opacity-50"
          >
            {loading ? "찾는 중…" : "📍 내 위치로 시작하기"}
          </button>

          <div>
            <p className="mb-3 text-sm font-semibold text-white/80">
              또는 위치를 직접 고르기
            </p>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {PRESETS.map((p) => (
                <button
                  key={p.name}
                  disabled={loading}
                  onClick={() => void loadPlaces(p.coords, p.name, radiusM)}
                  className="card rounded-xl px-3 py-3 text-sm font-semibold text-white/85 transition hover:bg-white/10 disabled:opacity-50"
                >
                  {p.name}
                </button>
              ))}
            </div>
          </div>
        </section>
      )}

      {(step === "play" || step === "result") && (
        <div className="lg:grid lg:grid-cols-[minmax(0,1fr)_340px] lg:items-start lg:gap-12">
          {/* ── 왼쪽: 게임 또는 결과 ── */}
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
              <div key={`${gameId}-${round}`} className="pop-in">
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
                    카카오맵에서 보기
                  </a>

                  <button onClick={share} className="btn-ghost">
                    {copied ? "복사됨!" : "공유하기"}
                  </button>
                </div>
              )
            )}
          </section>

          {/* ── 오른쪽: 후보 목록과 조작 ── */}
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

            <button
              onClick={playAgain}
              disabled={running}
              className="btn-ghost"
            >
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
