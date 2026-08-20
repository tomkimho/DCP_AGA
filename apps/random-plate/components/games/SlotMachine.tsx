"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { GameProps } from "@/lib/games";
import * as sound from "@/lib/sound";

const ITEM_H = 64; // px — 릴 한 칸 높이. translateY 계산에 쓰이므로 인라인 스타일과 일치시킨다
const STRIP_LEN = 28;
const WIN_AT = 24; // 스트립에서 당첨 항목이 놓이는 위치
const REEL_MS = [1500, 2100, 2700];

/** 릴 하나에 흘려보낼 이름 목록. 당첨 이름은 WIN_AT 자리에 심는다 */
function buildStrip(names: string[], winner: string, seed: number): string[] {
  const strip: string[] = [];
  for (let i = 0; i < STRIP_LEN; i++) {
    strip.push(names[(i * 7 + seed * 3) % names.length] ?? "");
  }
  strip[WIN_AT] = winner;
  return strip;
}

export default function SlotMachine({
  slots,
  onResult,
  onRunningChange,
}: GameProps) {
  const [running, setRunning] = useState(false);
  const [stopped, setStopped] = useState([false, false, false]);
  const [target, setTarget] = useState<number | null>(null);
  /** 0이면 정지 위치, WIN_AT이면 당첨 위치. 트랜지션은 이 값이 바뀔 때만 건다 */
  const [offset, setOffset] = useState(0);
  const [animate, setAnimate] = useState(false);

  const timers = useRef<number[]>([]);
  const rafs = useRef<number[]>([]);
  const stopWhir = useRef<() => void>(() => {});

  useEffect(
    () => () => {
      timers.current.forEach(clearTimeout);
      rafs.current.forEach(cancelAnimationFrame);
      stopWhir.current();
    },
    []
  );

  const names = useMemo(() => slots.map((s) => s.name), [slots]);

  const strips = useMemo(
    () =>
      [0, 1, 2].map((r) =>
        buildStrip(names, target === null ? (names[0] ?? "") : names[target], r)
      ),
    [names, target]
  );

  const spin = useCallback(() => {
    if (running || slots.length === 0) return;
    sound.unlock();
    sound.blip();

    const idx = Math.floor(Math.random() * slots.length);

    // 1) 트랜지션을 끄고 시작 위치로 되돌린다 (재시작 시 되감기가 보이지 않게)
    setAnimate(false);
    setOffset(0);
    setTarget(idx);
    setStopped([false, false, false]);
    setRunning(true);
    onRunningChange(true);

    // 2) 되감기가 화면에 반영된 다음 프레임에 트랜지션을 켜고 목표로 보낸다.
    //    같은 커밋에서 둘 다 바꾸면 브라우저가 트랜지션을 생략한다.
    rafs.current.push(
      requestAnimationFrame(() => {
        rafs.current.push(
          requestAnimationFrame(() => {
            setAnimate(true);
            setOffset(WIN_AT);
          })
        );
      })
    );

    stopWhir.current = sound.whir();

    timers.current = REEL_MS.map((ms, r) =>
      window.setTimeout(() => {
        sound.clunk();
        setStopped((s) => {
          const next = [...s];
          next[r] = true;
          return next;
        });
        if (r === REEL_MS.length - 1) {
          stopWhir.current();
          setRunning(false);
          onRunningChange(false);
          onResult(idx);
        }
      }, ms)
    );
  }, [running, slots.length, onResult, onRunningChange]);

  return (
    <div className="flex w-full flex-col items-center gap-6">
      <div className="w-full max-w-[min(90vw,360px)] rounded-3xl border border-white/10 bg-gradient-to-b from-white/10 to-white/[0.03] p-4 shadow-2xl lg:max-w-[420px]">
        <div className="grid grid-cols-3 gap-2">
          {strips.map((strip, r) => (
            <div
              key={r}
              className="relative overflow-hidden rounded-xl bg-black/60 ring-1 ring-white/10"
              style={{ height: ITEM_H }}
            >
              <div
                style={{
                  transform: `translateY(-${offset * ITEM_H}px)`,
                  transition: animate
                    ? `transform ${REEL_MS[r]}ms cubic-bezier(0.16,0.78,0.18,1)`
                    : "none",
                }}
              >
                {strip.map((name, i) => (
                  <div
                    key={i}
                    className="flex items-center justify-center px-1 text-center text-[11px] font-bold leading-tight text-white/85"
                    style={{ height: ITEM_H }}
                  >
                    <span className="line-clamp-2">{name}</span>
                  </div>
                ))}
              </div>

              {stopped[r] && (
                <div className="pointer-events-none absolute inset-0 rounded-xl ring-2 ring-amber-300/70" />
              )}
            </div>
          ))}
        </div>

        <p className="mt-3 text-center text-[11px] font-bold tracking-[0.3em] text-white/35">
          {running ? "SPINNING" : "7 7 7"}
        </p>
      </div>

      <button onClick={spin} disabled={running} className="btn-primary w-full">
        {running ? "돌리는 중…" : "🎰 레버 당기기"}
      </button>
    </div>
  );
}
