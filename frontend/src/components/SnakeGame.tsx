"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { X } from "lucide-react";

const GRID = 20;
const BASE_CELL = 16;
const INITIAL_SPEED = 150;

type Dir = "UP" | "DOWN" | "LEFT" | "RIGHT";
type Pos = { x: number; y: number };

interface SnakeGameProps {
  onClose: () => void;
  onUnlock: () => void;
}

export default function SnakeGame({ onClose, onUnlock }: SnakeGameProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [gameState, setGameState] = useState<"menu" | "playing" | "over" | "unlocked">("menu");
  const [score, setScore] = useState(0);
  const [level, setLevel] = useState(1);
  const [highScore, setHighScore] = useState(() => {
    if (typeof window !== "undefined") {
      const stored = localStorage.getItem("qwen-studio-snake-hi");
      return stored ? parseInt(stored, 10) : 0;
    }
    return 0;
  });

  const snakeRef = useRef<Pos[]>([{ x: 10, y: 10 }]);
  const dirRef = useRef<Dir>("RIGHT");
  const nextDirRef = useRef<Dir>("RIGHT");
  const foodRef = useRef<Pos>({ x: 15, y: 10 });
  const scoreRef = useRef(0);
  const levelRef = useRef(1);
  const loopRef = useRef<number | null>(null);
  const unlockedRef = useRef(false);
  const touchStartRef = useRef<{ x: number; y: number } | null>(null);

  // Responsive cell size
  const [CELL, setCELL] = useState(BASE_CELL);
  useEffect(() => {
    const updateSize = () => {
      const maxW = Math.min(window.innerWidth - 48, 400);
      setCELL(Math.floor(maxW / GRID));
    };
    updateSize();
    window.addEventListener("resize", updateSize);
    return () => window.removeEventListener("resize", updateSize);
  }, []);

  const spawnFood = useCallback(() => {
    const snake = snakeRef.current;
    let pos: Pos;
    do {
      pos = { x: Math.floor(Math.random() * GRID), y: Math.floor(Math.random() * GRID) };
    } while (snake.some(s => s.x === pos.x && s.y === pos.y));
    foodRef.current = pos;
  }, []);

  const resetGame = useCallback(() => {
    snakeRef.current = [{ x: 10, y: 10 }];
    dirRef.current = "RIGHT";
    nextDirRef.current = "RIGHT";
    scoreRef.current = 0;
    levelRef.current = 1;
    setScore(0);
    setLevel(1);
    spawnFood();
  }, [spawnFood]);

  const gameLoop = useCallback(() => {
    const snake = [...snakeRef.current];
    dirRef.current = nextDirRef.current;
    const head = { ...snake[0] };

    switch (dirRef.current) {
      case "UP": head.y--; break;
      case "DOWN": head.y++; break;
      case "LEFT": head.x--; break;
      case "RIGHT": head.x++; break;
    }

    // Wall collision
    if (head.x < 0 || head.x >= GRID || head.y < 0 || head.y >= GRID) {
      setGameState("over");
      return;
    }

    // Self collision
    if (snake.some(s => s.x === head.x && s.y === head.y)) {
      setGameState("over");
      return;
    }

    snake.unshift(head);

    // Food eaten
    if (head.x === foodRef.current.x && head.y === foodRef.current.y) {
      scoreRef.current++;
      const newLevel = Math.floor(scoreRef.current / 10) + 1;
      levelRef.current = newLevel;
      setScore(scoreRef.current);
      setLevel(newLevel);
      setHighScore(h => {
        const newHi = Math.max(h, scoreRef.current);
        if (typeof window !== "undefined") localStorage.setItem("qwen-studio-snake-hi", String(newHi));
        return newHi;
      });
      spawnFood();

      // Check unlock condition: level 5 with 10+ points (i.e., score >= 40 since level 5 starts at score 40)
      if (newLevel >= 5 && scoreRef.current >= 10 && !unlockedRef.current) {
        unlockedRef.current = true;
        setGameState("unlocked");
        onUnlock();
        return;
      }
    } else {
      snake.pop();
    }

    snakeRef.current = snake;
  }, [spawnFood, onUnlock]);

  // Render
  const render = useCallback(() => {
    const ctx = canvasRef.current?.getContext("2d");
    if (!ctx) return;
    const W = GRID * CELL;

    // Background
    ctx.fillStyle = "#0a0a0a";
    ctx.fillRect(0, 0, W, W);

    // Grid lines (subtle)
    ctx.strokeStyle = "rgba(255,255,255,0.03)";
    ctx.lineWidth = 0.5;
    for (let i = 0; i <= GRID; i++) {
      ctx.beginPath(); ctx.moveTo(i * CELL, 0); ctx.lineTo(i * CELL, W); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(0, i * CELL); ctx.lineTo(W, i * CELL); ctx.stroke();
    }

    // Food
    const food = foodRef.current;
    ctx.fillStyle = "#ff4444";
    ctx.shadowColor = "#ff4444";
    ctx.shadowBlur = 8;
    ctx.fillRect(food.x * CELL + 2, food.y * CELL + 2, CELL - 4, CELL - 4);
    ctx.shadowBlur = 0;

    // Snake
    const snake = snakeRef.current;
    snake.forEach((seg, i) => {
      const isHead = i === 0;
      ctx.fillStyle = isHead ? "#00ff88" : `rgba(0, 255, 136, ${0.9 - i * 0.02})`;
      if (isHead) {
        ctx.shadowColor = "#00ff88";
        ctx.shadowBlur = 12;
      }
      ctx.fillRect(seg.x * CELL + 1, seg.y * CELL + 1, CELL - 2, CELL - 2);
      ctx.shadowBlur = 0;
    });

    // Scanlines
    ctx.fillStyle = "rgba(0,0,0,0.15)";
    for (let y = 0; y < W; y += 4) {
      ctx.fillRect(0, y, W, 2);
    }
  }, []);

  // Game tick
  useEffect(() => {
    if (gameState !== "playing") {
      if (loopRef.current) clearInterval(loopRef.current);
      return;
    }

    const speed = Math.max(50, INITIAL_SPEED - (levelRef.current - 1) * 20);
    loopRef.current = window.setInterval(() => {
      gameLoop();
      render();
    }, speed);

    return () => { if (loopRef.current) clearInterval(loopRef.current); };
  }, [gameState, level, gameLoop, render]);

  // Keyboard input
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (gameState === "menu") {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          resetGame();
          setGameState("playing");
        }
        return;
      }
      if (gameState === "over") {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          resetGame();
          setGameState("playing");
        }
        return;
      }
      if (gameState !== "playing") return;

      const dir = dirRef.current;
      switch (e.key) {
        case "ArrowUp": case "w": case "W":
          if (dir !== "DOWN") nextDirRef.current = "UP"; break;
        case "ArrowDown": case "s": case "S":
          if (dir !== "UP") nextDirRef.current = "DOWN"; break;
        case "ArrowLeft": case "a": case "A":
          if (dir !== "RIGHT") nextDirRef.current = "LEFT"; break;
        case "ArrowRight": case "d": case "D":
          if (dir !== "LEFT") nextDirRef.current = "RIGHT"; break;
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [gameState, resetGame]);

  // Touch swipe controls
  useEffect(() => {
    if (gameState !== "playing") return;
    const onTouchStart = (e: TouchEvent) => {
      touchStartRef.current = { x: e.touches[0].clientX, y: e.touches[0].clientY };
    };
    const onTouchEnd = (e: TouchEvent) => {
      if (!touchStartRef.current) return;
      const dx = e.changedTouches[0].clientX - touchStartRef.current.x;
      const dy = e.changedTouches[0].clientY - touchStartRef.current.y;
      const dir = dirRef.current;
      if (Math.abs(dx) > Math.abs(dy) && Math.abs(dx) > 20) {
        if (dx > 0 && dir !== "LEFT") nextDirRef.current = "RIGHT";
        else if (dx < 0 && dir !== "RIGHT") nextDirRef.current = "LEFT";
      } else if (Math.abs(dy) > 20) {
        if (dy > 0 && dir !== "UP") nextDirRef.current = "DOWN";
        else if (dy < 0 && dir !== "DOWN") nextDirRef.current = "UP";
      }
      touchStartRef.current = null;
    };
    window.addEventListener("touchstart", onTouchStart, { passive: true });
    window.addEventListener("touchend", onTouchEnd, { passive: true });
    return () => {
      window.removeEventListener("touchstart", onTouchStart);
      window.removeEventListener("touchend", onTouchEnd);
    };
  }, [gameState]);

  // Initial render for menu
  useEffect(() => { render(); }, [render]);

  const W = GRID * CELL;

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
      <div className="relative bg-[#0a0a0a] border-2 border-[#00ff88]/30 rounded-2xl p-4 sm:p-6 shadow-[0_0_60px_rgba(0,255,136,0.1)] max-w-full">
        <button
          onClick={onClose}
          className="absolute top-3 right-3 p-1 text-white/20 hover:text-white/60 transition-colors"
        >
          <X size={16} />
        </button>

        {/* HUD */}
        <div className="flex justify-between items-center mb-4 px-1">
          <div className="font-mono text-[10px] uppercase tracking-widest text-[#00ff88]/60">
            Snake Console v1.0
          </div>
          <div className="flex gap-4 font-mono text-xs">
            <span className="text-white/40">LVL <span className="text-[#00ff88]">{level}</span></span>
            <span className="text-white/40">SCORE <span className="text-[#00ff88]">{score}</span></span>
            <span className="text-white/40">HI <span className="text-yellow-500">{highScore}</span></span>
          </div>
        </div>

        {/* Canvas */}
        <div className="relative rounded-lg overflow-hidden border border-white/10">
          <canvas
            ref={canvasRef}
            width={W}
            height={W}
            className="block"
            style={{ imageRendering: "pixelated" }}
          />

          {/* Overlays */}
          {gameState === "menu" && (
            <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/70">
              <div className="text-[#00ff88] text-3xl font-bold mb-2 animate-pulse" style={{ textShadow: "0 0 20px #00ff88" }}>
                SNAKE
              </div>
              <div className="text-white/30 text-xs font-mono mb-1">Reach Level 5 to unlock a secret</div>
              <div className="text-white/20 text-[10px] font-mono mb-6">Arrow keys, WASD, or swipe to move</div>
              <button
                onClick={() => { resetGame(); setGameState("playing"); }}
                className="px-6 py-2 bg-[#00ff88] text-black font-bold text-sm uppercase tracking-widest rounded hover:bg-white transition-colors"
              >
                Start
              </button>
            </div>
          )}

          {gameState === "over" && (
            <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/80">
              <div className="text-red-500 text-2xl font-bold mb-1" style={{ textShadow: "0 0 15px #ff0000" }}>
                GAME OVER
              </div>
              <div className="text-white/40 text-sm font-mono mb-1">Score: {score} | Level: {level}</div>
              <div className="text-white/20 text-[10px] font-mono mb-4">
                {level < 5 ? `Need Level 5 to unlock (${5 - level} more)` : "So close! Try again."}
              </div>
              <button
                onClick={() => { resetGame(); setGameState("playing"); }}
                className="px-6 py-2 bg-[#00ff88] text-black font-bold text-sm uppercase tracking-widest rounded hover:bg-white transition-colors"
              >
                Retry
              </button>
            </div>
          )}

          {gameState === "unlocked" && (
            <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/80">
              <div className="relative">
                <div className="text-[#00ff88] text-3xl font-bold mb-2 animate-pulse" style={{ textShadow: "0 0 30px #00ff88, 0 0 60px #00ff88" }}>
                  ACCESS GRANTED
                </div>
                <div className="absolute inset-0 text-[#00ff88] text-3xl font-bold opacity-20 blur-sm" style={{ textShadow: "0 0 40px #00ff88" }}>
                  ACCESS GRANTED
                </div>
              </div>
              <div className="text-white/60 text-sm font-mono mb-1 mt-2">Secret kasset unlocked!</div>
              <div className="text-white/30 text-[10px] font-mono mb-6">Check the kasset carousel</div>
              <button
                onClick={onClose}
                className="px-6 py-2 bg-[#00ff88] text-black font-bold text-sm uppercase tracking-widest rounded hover:bg-white transition-colors"
              >
                Continue
              </button>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="mt-3 flex justify-between items-center px-1">
          <div className="text-[9px] text-white/15 font-mono">10 pts per level | speed increases</div>
          <div className="text-[9px] text-white/15 font-mono hidden sm:block">press SPACE or ENTER to start</div>
          <div className="text-[9px] text-white/15 font-mono sm:hidden">swipe to steer</div>
        </div>
      </div>
    </div>
  );
}
