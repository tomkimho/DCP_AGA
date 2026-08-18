"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Wheel, { COLORS, SECTORS } from "@/components/Wheel";
import Confetti from "@/components/Confetti";
import { walkMinutes } from "@/lib/grid";
import type { Coords, Place, PlacesResponse } from "@/lib/types";

type Step = "location" | "spin" | "result";

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

  const [slots, setSlots] = useState<Place[]>([]);
  const [targetIndex, setTargetIndex] = useState(0);
  const [spinning, setSpinning] = useState(false);
  const [winner, setWinner] = useState<Place | null>(null);
  const [rerolls, setRerolls] = useState(0);
  const [confettiKey, setConfettiKey] = useState(0);
  const [copied, setCopied] = useState(false);

  const meal = useMemo(() => mealLabel(), []);
  const apiCalls = useRef(0);

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
        setSlots(shuffle(data.places).slice(0, SECTORS));
        setRerolls(0);
        setStep("spin");
      } catch (e) {
        setError(e instanceof Error ? e.message : "알 수 없는 오류");
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const useGps = useCallback(() => {
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

  const spin = useCallback(() => {
    if (spinning || slots.length === 0) return;
    setWinner(null);
    setTargetIndex(Math.floor(Math.random() * Math.min(SECTORS, slots.length)));
    setSpinning(true);
  }, [spinning, slots.length]);

  const onSettled = useCallback(() => {
    if (!spinning) return;
    setSpinning(false);
    const picked = slots[targetIndex];
    if (picked) {
      setWinner(picked);
      setConfettiKey((k) => k + 1);
      setStep("result");
    }
  }, [spinning, slots, targetIndex]);

  /** 리롤 — 고정된 후보 풀 안에서만 다시 뽑으므로 API 호출이 발생하지 않는다 */
  const reroll = useCallback(() => {
    setWinner(null);
    setSlots(shuffle(pool).slice(0, SECTORS));
    setRerolls((n) => n + 1);
    setStep("spin");
  }, [pool]);

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

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-md flex-col px-5 pb-10 pt-8">
      <Confetti fire={confettiKey} />

      <header className="mb-7">
        <h1 className="text-2xl font-black tracking-tight">
          Random&nbsp;Plate
          <span className="ml-2 align-middle text-[11px] font-bold text-white/40">
            v0
          </span>
        </h1>
        <p className="mt-1 text-sm text-white/55">
          오늘 {meal} 뭐 먹지? 룰렛 한 번이면 끝.
        </p>
      </header>

      {error && (
        <div className="mb-4 rounded-xl border border-red-400/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">
          {error}
        </div>
      )}

      {step === "location" && (
        <section className="pop-in flex flex-col gap-6">
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
            <div className="grid grid-cols-2 gap-2">
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

      {(step === "spin" || step === "result") && (
        <section className="pop-in flex flex-1 flex-col">
          <div className="mb-4 flex items-center justify-between text-xs text-white/50">
            <span>
              {placeLabel} · 반경 {radiusM}m · 후보 {pool.length}곳
            </span>
            <button
              onClick={() => {
                setStep("location");
                setWinner(null);
              }}
              className="underline underline-offset-2 hover:text-white/80"
            >
              위치 변경
            </button>
          </div>

          <Wheel
            slots={slots}
            spinning={spinning}
            targetIndex={targetIndex}
            onSettled={onSettled}
          />

          {step === "spin" && (
            <ol className="mt-6 grid grid-cols-2 gap-x-3 gap-y-2.5">
              {slots.map((p, i) => (
                <li
                  key={p.id}
                  data-slot={i}
                  className="flex items-center gap-2 overflow-hidden"
                >
                  <span
                    className="grid h-5 w-5 shrink-0 place-items-center rounded-md text-[11px] font-black text-black"
                    style={{ background: COLORS[i % COLORS.length] }}
                  >
                    {i + 1}
                  </span>
                  <span className="truncate text-[13px] font-semibold text-white/80">
                    {p.name}
                  </span>
                </li>
              ))}
            </ol>
          )}

          {step === "spin" && (
            <div className="mt-7 flex flex-col gap-3">
              <button
                onClick={spin}
                disabled={spinning}
                className="rounded-2xl bg-white px-5 py-4 text-base font-black text-black transition active:scale-[0.98] disabled:opacity-50"
              >
                {spinning ? "돌리는 중…" : "🎡 돌리기"}
              </button>
              <button
                onClick={reroll}
                disabled={spinning}
                className="rounded-2xl border border-white/15 bg-white/5 px-5 py-3 text-sm font-bold text-white/75 transition hover:bg-white/10 disabled:opacity-40"
              >
                후보 8곳 다시 뽑기
              </button>
            </div>
          )}

          {step === "result" && winner && (
            <div className="pop-in mt-7 flex flex-col gap-4">
              <div className="card rounded-2xl px-5 py-5">
                <p className="text-xs font-bold tracking-wide text-fuchsia-300">
                  오늘의 {meal}
                </p>
                <h2 className="mt-1 text-2xl font-black leading-tight">
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

              <a
                href={winner.placeUrl}
                target="_blank"
                rel="noreferrer noopener"
                className="rounded-2xl bg-[#ffe812] px-5 py-4 text-center text-base font-black text-black transition active:scale-[0.98]"
              >
                카카오맵에서 보기
              </a>

              <div className="grid grid-cols-2 gap-3">
                <button
                  onClick={share}
                  className="rounded-2xl border border-white/15 bg-white/5 px-4 py-3 text-sm font-bold transition hover:bg-white/10"
                >
                  {copied ? "복사됨!" : "공유하기"}
                </button>
                <button
                  onClick={reroll}
                  className="rounded-2xl border border-white/15 bg-white/5 px-4 py-3 text-sm font-bold transition hover:bg-white/10"
                >
                  다시 정하기
                </button>
              </div>
            </div>
          )}

          <p className="mt-6 text-center text-[11px] leading-relaxed text-white/35">
            리롤 {rerolls}회 · 이번 세션 외부 API 호출{" "}
            <b className="text-white/60">{apiCalls.current}회</b>
            <br />
            (후보 풀을 고정해 두므로 다시 뽑아도 호출이 늘지 않습니다)
          </p>
        </section>
      )}

      <footer className="mt-auto pt-8 text-center text-[11px] leading-relaxed text-white/30">
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
