/**
 * 외부 오디오 파일 없이 Web Audio API로 효과음을 합성한다.
 *
 * mp3를 넣지 않은 이유: 번들 용량이 늘고, 저작권 확인이 필요하고,
 * 오프라인/CSP 환경에서 깨진다. 합성음은 그 셋 다 해당이 없다.
 *
 * 브라우저는 사용자 제스처 이전의 오디오 재생을 막으므로,
 * 첫 클릭에서 unlock()을 반드시 호출해야 한다.
 */

let ctx: AudioContext | null = null;
let master: GainNode | null = null;
let noise: AudioBuffer | null = null;
let muted = false;

const listeners = new Set<(m: boolean) => void>();

function ac(): AudioContext | null {
  if (typeof window === "undefined") return null;
  if (!ctx) {
    const AC =
      window.AudioContext ??
      (window as unknown as { webkitAudioContext?: typeof AudioContext })
        .webkitAudioContext;
    if (!AC) return null;
    ctx = new AC();
    master = ctx.createGain();
    master.gain.value = 0.55;
    master.connect(ctx.destination);

    // 1초짜리 화이트노이즈 — 틱, 총성, 카드 소리의 재료
    noise = ctx.createBuffer(1, ctx.sampleRate, ctx.sampleRate);
    const d = noise.getChannelData(0);
    for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
  }
  if (ctx.state === "suspended") void ctx.resume();
  return ctx;
}

/** 첫 사용자 제스처에서 호출 — 이후 재생이 허용된다 */
export function unlock() {
  ac();
}

export function isMuted() {
  return muted;
}

export function toggleMute() {
  muted = !muted;
  try {
    localStorage.setItem("rp-muted", muted ? "1" : "0");
  } catch {
    /* 프라이빗 모드 등에서 localStorage가 막힌 경우 — 무시 */
  }
  listeners.forEach((l) => l(muted));
  return muted;
}

export function loadMutePref() {
  try {
    muted = localStorage.getItem("rp-muted") === "1";
  } catch {
    muted = false;
  }
  listeners.forEach((l) => l(muted));
}

export function onMuteChange(fn: (m: boolean) => void) {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

function ready(): [AudioContext, GainNode] | null {
  if (muted) return null;
  const c = ac();
  if (!c || !master) return null;
  return [c, master];
}

function noiseSource(c: AudioContext): AudioBufferSourceNode {
  const s = c.createBufferSource();
  s.buffer = noise;
  return s;
}

/** 감쇠 포락선 — exponentialRamp는 0을 못 받으므로 0.0001로 수렴시킨다 */
function decay(
  g: GainNode,
  t: number,
  peak: number,
  attack: number,
  rel: number
) {
  g.gain.setValueAtTime(0.0001, t);
  g.gain.exponentialRampToValueAtTime(peak, t + attack);
  g.gain.exponentialRampToValueAtTime(0.0001, t + attack + rel);
}

/** 룰렛 핀이 튕기는 소리. vel 0~1로 세기 조절 */
export function tick(vel = 1) {
  const r = ready();
  if (!r) return;
  const [c, out] = r;
  const t = c.currentTime;

  const src = noiseSource(c);
  const bp = c.createBiquadFilter();
  bp.type = "bandpass";
  bp.frequency.value = 1800 + 900 * vel;
  bp.Q.value = 6;
  const g = c.createGain();
  decay(g, t, 0.05 + 0.11 * vel, 0.001, 0.035);

  src.connect(bp).connect(g).connect(out);
  src.start(t);
  src.stop(t + 0.06);
}

/** 슬롯 릴이 도는 동안의 지속음. 반환된 함수를 호출하면 멈춘다 */
export function whir(): () => void {
  const r = ready();
  if (!r) return () => {};
  const [c, out] = r;
  const t = c.currentTime;

  const osc = c.createOscillator();
  osc.type = "sawtooth";
  osc.frequency.setValueAtTime(58, t);

  const lp = c.createBiquadFilter();
  lp.type = "lowpass";
  lp.frequency.setValueAtTime(900, t);

  const g = c.createGain();
  g.gain.setValueAtTime(0.0001, t);
  g.gain.exponentialRampToValueAtTime(0.05, t + 0.08);

  osc.connect(lp).connect(g).connect(out);
  osc.start(t);

  return () => {
    const now = c.currentTime;
    g.gain.cancelScheduledValues(now);
    g.gain.setValueAtTime(Math.max(g.gain.value, 0.0001), now);
    g.gain.exponentialRampToValueAtTime(0.0001, now + 0.08);
    osc.stop(now + 0.12);
  };
}

/** 릴이 한 칸 물리며 멈추는 소리 */
export function clunk() {
  const r = ready();
  if (!r) return;
  const [c, out] = r;
  const t = c.currentTime;

  const osc = c.createOscillator();
  osc.type = "triangle";
  osc.frequency.setValueAtTime(220, t);
  osc.frequency.exponentialRampToValueAtTime(90, t + 0.09);
  const g = c.createGain();
  decay(g, t, 0.2, 0.002, 0.1);
  osc.connect(g).connect(out);
  osc.start(t);
  osc.stop(t + 0.14);

  tick(0.5);
}

/** 공이치기를 젖히는 두 번의 금속음 */
export function cock() {
  tick(0.9);
  window.setTimeout(() => tick(0.7), 110);
}

/** 총성 — 노이즈 파열음 + 저역 충격 */
export function bang() {
  const r = ready();
  if (!r) return;
  const [c, out] = r;
  const t = c.currentTime;

  const src = noiseSource(c);
  const lp = c.createBiquadFilter();
  lp.type = "lowpass";
  lp.frequency.setValueAtTime(6000, t);
  lp.frequency.exponentialRampToValueAtTime(300, t + 0.32);
  const g = c.createGain();
  decay(g, t, 0.65, 0.002, 0.34);
  src.connect(lp).connect(g).connect(out);
  src.start(t);
  src.stop(t + 0.4);

  const thump = c.createOscillator();
  thump.type = "sine";
  thump.frequency.setValueAtTime(120, t);
  thump.frequency.exponentialRampToValueAtTime(38, t + 0.22);
  const tg = c.createGain();
  decay(tg, t, 0.55, 0.004, 0.26);
  thump.connect(tg).connect(out);
  thump.start(t);
  thump.stop(t + 0.32);
}

/** 빈 약실 — 아무 일도 없을 때의 허탈한 딸깍 */
export function dryFire() {
  const r = ready();
  if (!r) return;
  const [c, out] = r;
  const t = c.currentTime;
  const osc = c.createOscillator();
  osc.type = "square";
  osc.frequency.setValueAtTime(380, t);
  osc.frequency.exponentialRampToValueAtTime(140, t + 0.05);
  const g = c.createGain();
  decay(g, t, 0.18, 0.001, 0.06);
  osc.connect(g).connect(out);
  osc.start(t);
  osc.stop(t + 0.09);
}

/** 카드를 뒤집는 바람 소리 */
export function swish() {
  const r = ready();
  if (!r) return;
  const [c, out] = r;
  const t = c.currentTime;

  const src = noiseSource(c);
  const bp = c.createBiquadFilter();
  bp.type = "bandpass";
  bp.frequency.setValueAtTime(700, t);
  bp.frequency.exponentialRampToValueAtTime(2600, t + 0.16);
  bp.Q.value = 1.4;
  const g = c.createGain();
  decay(g, t, 0.16, 0.02, 0.15);
  src.connect(bp).connect(g).connect(out);
  src.start(t);
  src.stop(t + 0.2);
}

/** 당첨 팡파르 — 4음 아르페지오 */
export function fanfare() {
  const r = ready();
  if (!r) return;
  const [c, out] = r;
  const t0 = c.currentTime;
  const notes = [523.25, 659.25, 783.99, 1046.5];

  notes.forEach((f, i) => {
    const t = t0 + i * 0.085;
    const osc = c.createOscillator();
    osc.type = "triangle";
    osc.frequency.setValueAtTime(f, t);
    const g = c.createGain();
    decay(g, t, 0.22, 0.008, i === notes.length - 1 ? 0.5 : 0.2);
    osc.connect(g).connect(out);
    osc.start(t);
    osc.stop(t + 0.7);
  });
}

/** 버튼 눌림 피드백 */
export function blip() {
  const r = ready();
  if (!r) return;
  const [c, out] = r;
  const t = c.currentTime;
  const osc = c.createOscillator();
  osc.type = "sine";
  osc.frequency.setValueAtTime(660, t);
  const g = c.createGain();
  decay(g, t, 0.09, 0.003, 0.05);
  osc.connect(g).connect(out);
  osc.start(t);
  osc.stop(t + 0.08);
}

/**
 * 룰렛 감속에 맞춰 틱을 예약한다.
 *
 * CSS transition의 cubic-bezier와 같은 곡선을 JS로 다시 계산해서,
 * 섹터 경계를 지나는 실제 시점마다 소리가 나게 한다.
 * 일정 간격으로 뿌리면 감속이 소리에 반영되지 않아 가짜처럼 들린다.
 */
export function scheduleWheelTicks(
  totalDeg: number,
  durationMs: number,
  sectorDeg: number
): () => void {
  const B = (p1: number, p2: number) => (s: number) =>
    3 * p1 * s * (1 - s) ** 2 + 3 * p2 * s ** 2 * (1 - s) + s ** 3;
  // globals.css의 cubic-bezier(0.12, 0.72, 0.13, 1)과 반드시 동일해야 한다
  const X = B(0.12, 0.13);
  const Y = B(0.72, 1);

  const total = Math.floor(totalDeg / sectorDeg);
  const timers: number[] = [];

  for (let k = 1; k <= total; k++) {
    const p = (k * sectorDeg) / totalDeg;
    if (p >= 1) break;

    // Y(s) = p 를 만족하는 s 를 이분 탐색 → 그 시점의 X(s)가 실제 시각
    let lo = 0;
    let hi = 1;
    for (let i = 0; i < 24; i++) {
      const mid = (lo + hi) / 2;
      if (Y(mid) < p) lo = mid;
      else hi = mid;
    }
    const at = X((lo + hi) / 2) * durationMs;
    timers.push(window.setTimeout(() => tick(Math.max(0.15, 1 - p)), at));
  }

  return () => timers.forEach(clearTimeout);
}
