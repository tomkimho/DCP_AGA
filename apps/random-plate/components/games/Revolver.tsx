"use client";

import { useEffect, useRef, useState } from "react";
import type { GameProps } from "@/lib/games";
import * as sound from "@/lib/sound";

const CHAMBERS = 6;
const ANGLE = 360 / CHAMBERS;
const SPIN_MS = 2200;
const CHAMBER_COLORS = [
  "#ff6b6b",
  "#ffa94d",
  "#ffd43b",
  "#69db7c",
  "#4dabf7",
  "#9775fa",
];

type Phase = "idle" | "spinning" | "armed" | "firing";

function point(r: number, clockDeg: number) {
  const rad = ((clockDeg - 90) * Math.PI) / 180;
  return [160 + r * Math.cos(rad), 160 + r * Math.sin(rad)] as const;
}

export default function Revolver({
  slots,
  onResult,
  onRunningChange,
}: GameProps) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [rotation, setRotation] = useState(0);
  const [flash, setFlash] = useState(false);
  const target = useRef(0);
  const cancelTicks = useRef<() => void>(() => {});
  const timers = useRef<number[]>([]);

  useEffect(
    () => () => {
      cancelTicks.current();
      timers.current.forEach(clearTimeout);
    },
    []
  );

  const spin = () => {
    if (phase !== "idle") return;
    sound.unlock();
    sound.blip();

    const idx = Math.floor(Math.random() * Math.min(CHAMBERS, slots.length));
    target.current = idx;

    const targetMod = (((-idx * ANGLE) % 360) + 360) % 360;
    const currentMod = ((rotation % 360) + 360) % 360;
    let delta = targetMod - currentMod;
    if (delta < 0) delta += 360;
    const total = 360 * 3 + delta;

    cancelTicks.current = sound.scheduleWheelTicks(total, SPIN_MS, ANGLE);
    setRotation((r) => r + total);
    setPhase("spinning");
    onRunningChange(true);
  };

  const armed = () => {
    if (phase !== "spinning") return;
    cancelTicks.current();
    setPhase("armed");
  };

  const fire = () => {
    if (phase !== "armed") return;
    setPhase("firing");
    sound.cock();

    // 방아쇠를 당기고 실제로 터지기까지의 뜸 — 이 침묵이 긴장을 만든다
    timers.current.push(
      window.setTimeout(() => {
        sound.bang();
        setFlash(true);
        timers.current.push(window.setTimeout(() => setFlash(false), 220));
        onRunningChange(false);
        onResult(target.current);
      }, 850)
    );
  };

  return (
    <div className="flex w-full flex-col items-center gap-6">
      <div className="relative mx-auto aspect-square w-full max-w-[min(84vw,320px)] select-none lg:max-w-[380px]">
        {/* 공이치기 위치 표시 */}
        <div className="absolute left-1/2 -top-1 z-10 -translate-x-1/2">
          <div
            className="h-0 w-0 drop-shadow-lg"
            style={{
              borderLeft: "11px solid transparent",
              borderRight: "11px solid transparent",
              borderTop: "22px solid #fff",
            }}
          />
        </div>

        {flash && (
          <div className="pointer-events-none absolute inset-0 z-20 animate-ping rounded-full bg-amber-200/40" />
        )}

        <svg
          viewBox="0 0 320 320"
          className="h-full w-full"
          style={{
            transform: `rotate(${rotation}deg)`,
            transition: `transform ${SPIN_MS}ms cubic-bezier(0.12,0.72,0.13,1)`,
          }}
          onTransitionEnd={armed}
          aria-hidden
        >
          <circle
            cx={160}
            cy={160}
            r={148}
            fill="#1a1a24"
            stroke="#3d3d52"
            strokeWidth={6}
          />
          <circle
            cx={160}
            cy={160}
            r={128}
            fill="none"
            stroke="#2a2a38"
            strokeWidth={2}
          />

          {Array.from({ length: CHAMBERS }).map((_, i) => {
            const [cx, cy] = point(88, i * ANGLE);
            const loaded = i < slots.length;
            return (
              <g key={i}>
                <circle
                  cx={cx}
                  cy={cy}
                  r={34}
                  fill={loaded ? CHAMBER_COLORS[i] : "#14141c"}
                  stroke="rgba(0,0,0,0.45)"
                  strokeWidth={3}
                />
                <circle
                  cx={cx}
                  cy={cy}
                  r={20}
                  fill="rgba(0,0,0,0.45)"
                />
                <text
                  x={cx}
                  y={cy}
                  textAnchor="middle"
                  dominantBaseline="central"
                  fill="#fff"
                  fontSize={20}
                  fontWeight={900}
                >
                  {i + 1}
                </text>
              </g>
            );
          })}

          <circle cx={160} cy={160} r={26} fill="#0b0b12" />
          <circle
            cx={160}
            cy={160}
            r={26}
            fill="none"
            stroke="#3d3d52"
            strokeWidth={4}
          />
        </svg>
      </div>

      {phase === "armed" ? (
        <button onClick={fire} className="btn-danger w-full">
          🔫 발사
        </button>
      ) : (
        <button
          onClick={spin}
          disabled={phase !== "idle"}
          className="btn-primary w-full"
        >
          {phase === "idle" ? "🔄 실린더 돌리기" : "돌리는 중…"}
        </button>
      )}

      <p className="-mt-3 text-center text-[11px] text-white/35">
        {phase === "armed"
          ? "실린더가 멈췄습니다. 방아쇠를 당기세요."
          : "실린더를 돌리면 약실 하나가 공이 앞에 섭니다."}
      </p>
    </div>
  );
}
