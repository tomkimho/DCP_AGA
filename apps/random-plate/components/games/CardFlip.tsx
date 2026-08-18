"use client";

import { useEffect, useRef, useState } from "react";
import type { GameProps } from "@/lib/games";
import * as sound from "@/lib/sound";

const BACK_COLORS = [
  "from-rose-500/80 to-rose-700/80",
  "from-amber-500/80 to-amber-700/80",
  "from-emerald-500/80 to-emerald-700/80",
  "from-sky-500/80 to-sky-700/80",
  "from-violet-500/80 to-violet-700/80",
];

export default function CardFlip({
  slots,
  onResult,
  onRunningChange,
}: GameProps) {
  const [picked, setPicked] = useState<number | null>(null);
  const [revealAll, setRevealAll] = useState(false);
  const timers = useRef<number[]>([]);

  useEffect(() => () => timers.current.forEach(clearTimeout), []);

  const pick = (i: number) => {
    if (picked !== null) return;
    sound.unlock();
    sound.swish();
    setPicked(i);
    onRunningChange(true);

    // 고른 카드가 먼저 뒤집히고, 나머지가 뒤따라 열린다
    timers.current.push(
      window.setTimeout(() => {
        sound.swish();
        setRevealAll(true);
      }, 480)
    );
    timers.current.push(
      window.setTimeout(() => {
        onRunningChange(false);
        onResult(i);
      }, 620)
    );
  };

  return (
    <div className="flex w-full flex-col items-center gap-5">
      <div className="grid w-full grid-cols-5 gap-2 sm:gap-3">
        {slots.map((place, i) => {
          const open = picked === i || revealAll;
          const isPick = picked === i;
          return (
            <button
              key={place.id}
              onClick={() => pick(i)}
              disabled={picked !== null}
              className={`card-flip aspect-[3/4] ${open ? "is-open" : ""} ${
                picked !== null && !isPick ? "opacity-45" : ""
              }`}
              aria-label={`${i + 1}번 카드`}
            >
              <span className="card-flip-inner">
                <span
                  className={`card-face card-back bg-gradient-to-br ${
                    BACK_COLORS[i % BACK_COLORS.length]
                  }`}
                >
                  <span className="text-xl font-black text-white/90 sm:text-2xl">
                    {i + 1}
                  </span>
                </span>
                <span className="card-face card-front">
                  <span className="line-clamp-3 px-1 text-[10px] font-bold leading-tight text-white/90 sm:text-xs">
                    {place.name}
                  </span>
                </span>
              </span>
            </button>
          );
        })}
      </div>

      <p className="text-center text-[11px] text-white/35">
        {picked === null
          ? "마음이 가는 카드를 한 장 고르세요."
          : "카드를 여는 중…"}
      </p>
    </div>
  );
}
