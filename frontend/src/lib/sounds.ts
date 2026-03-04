/**
 * Retro-futuristic sound engine using Web Audio API.
 * All sounds are synthesized — no external files needed.
 * Designed to be subtle, tasteful, and non-intrusive.
 */

let audioCtx: AudioContext | null = null;
let _muted = false;

function getCtx(): AudioContext {
  if (!audioCtx) {
    audioCtx = new AudioContext();
  }
  if (audioCtx.state === "suspended") {
    audioCtx.resume();
  }
  return audioCtx;
}

export function setMuted(muted: boolean) {
  _muted = muted;
  if (typeof window !== "undefined") {
    localStorage.setItem("qwen-studio-muted", muted ? "1" : "0");
  }
}

export function isMuted(): boolean {
  if (typeof window !== "undefined" && _muted === false) {
    const stored = localStorage.getItem("qwen-studio-muted");
    if (stored === "1") _muted = true;
  }
  return _muted;
}

// ─── Utility ───

function playTone(
  freq: number,
  duration: number,
  volume: number = 0.08,
  type: OscillatorType = "sine",
  fadeOut: number = 0.05,
) {
  if (isMuted()) return;
  try {
    const ctx = getCtx();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = type;
    osc.frequency.setValueAtTime(freq, ctx.currentTime);
    gain.gain.setValueAtTime(volume, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + duration);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start(ctx.currentTime);
    osc.stop(ctx.currentTime + duration + fadeOut);
  } catch {
    // Audio not available
  }
}

function playNoise(duration: number, volume: number = 0.02) {
  if (isMuted()) return;
  try {
    const ctx = getCtx();
    const bufferSize = ctx.sampleRate * duration;
    const buffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate);
    const data = buffer.getChannelData(0);
    for (let i = 0; i < bufferSize; i++) {
      data[i] = (Math.random() * 2 - 1) * volume;
    }
    const source = ctx.createBufferSource();
    const gain = ctx.createGain();
    source.buffer = buffer;
    gain.gain.setValueAtTime(volume, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + duration);
    source.connect(gain);
    gain.connect(ctx.destination);
    source.start();
  } catch {
    // Audio not available
  }
}

// ─── Sound Effects ───

/** Soft click when user sends a message */
export function soundSend() {
  playTone(800, 0.06, 0.05, "square");
  setTimeout(() => playTone(1000, 0.04, 0.03, "square"), 30);
}

/** Subtle low hum when thinking starts */
export function soundThinkStart() {
  playTone(220, 0.3, 0.03, "sine");
  playTone(330, 0.2, 0.02, "sine");
}

/** Gentle chime when thinking completes */
export function soundThinkEnd() {
  playTone(660, 0.1, 0.04, "sine");
  setTimeout(() => playTone(880, 0.15, 0.03, "sine"), 60);
}

/** Mechanical click for tool execution start */
export function soundToolStart() {
  playNoise(0.04, 0.06);
  playTone(440, 0.05, 0.04, "square");
}

/** Brief confirmation blip when tool completes */
export function soundToolDone() {
  playTone(520, 0.06, 0.03, "triangle");
  setTimeout(() => playTone(780, 0.08, 0.03, "triangle"), 50);
}

/** Soft ascending chime when response is complete */
export function soundDone() {
  playTone(523, 0.12, 0.04, "sine");
  setTimeout(() => playTone(659, 0.12, 0.04, "sine"), 80);
  setTimeout(() => playTone(784, 0.18, 0.04, "sine"), 160);
}

/** Low buzz for errors */
export function soundError() {
  playTone(150, 0.15, 0.06, "sawtooth");
  setTimeout(() => playTone(120, 0.2, 0.05, "sawtooth"), 100);
}

/** Cartridge insert — retro boot chime */
export function soundCartridgeInsert() {
  playTone(262, 0.08, 0.05, "square");
  setTimeout(() => playTone(330, 0.08, 0.05, "square"), 80);
  setTimeout(() => playTone(392, 0.08, 0.05, "square"), 160);
  setTimeout(() => playTone(523, 0.2, 0.06, "square"), 240);
}

/** Cartridge eject — descending tone */
export function soundCartridgeEject() {
  playTone(523, 0.06, 0.04, "square");
  setTimeout(() => playTone(392, 0.06, 0.04, "square"), 60);
  setTimeout(() => playTone(262, 0.1, 0.03, "square"), 120);
}

/** Subtle tick for UI interactions (drawer open, toggle, etc) */
export function soundTick() {
  playTone(600, 0.03, 0.03, "square");
}

/** New chat — fresh start */
export function soundNewChat() {
  playTone(440, 0.06, 0.04, "triangle");
  setTimeout(() => playTone(660, 0.1, 0.04, "triangle"), 60);
}
