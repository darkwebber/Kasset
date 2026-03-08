"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { X, BarChart3 } from "lucide-react";
import { soundSnakeEat, soundSnakeCrash, soundSnakeTurn, soundSnakeLevelUp, soundSnakeUnlock, soundSnakeStart } from "@/lib/sounds";
import { getSnakeStats, saveSnakeGame, getAverageScore, getRecentGames, getAchievementInfo } from "@/lib/snakeStats";

const GRID = 20;
const BASE_CELL = 16;
const INITIAL_SPEED = 150;

type Dir = "UP" | "DOWN" | "LEFT" | "RIGHT";
type Pos = { x: number; y: number };

interface SnakeGameProps {
  onClose: () => void;
  onUnlock: () => void;
}

// Convert HSL to RGB
function hslToRgb(h: number, s: number, l: number) {
  h = h / 360;
  s = s / 100;
  l = l / 100;
  
  let r, g, b;
  
  if (s === 0) {
    r = g = b = l;
  } else {
    const hue2rgb = (p: number, q: number, t: number) => {
      if (t < 0) t += 1;
      if (t > 1) t -= 1;
      if (t < 1/6) return p + (q - p) * 6 * t;
      if (t < 1/2) return q;
      if (t < 2/3) return p + (q - p) * (2/3 - t) * 6;
      return p;
    };
    
    const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
    const p = 2 * l - q;
    r = hue2rgb(p, q, h + 1/3);
    g = hue2rgb(p, q, h);
    b = hue2rgb(p, q, h - 1/3);
  }
  
  return {
    r: Math.round(r * 255),
    g: Math.round(g * 255),
    b: Math.round(b * 255)
  };
}

// Generate random color theme based on rotating the color wheel
function generateRandomTheme() {
  // Base colors: green (120°) and red (0°) are opposite on color wheel
  const baseHue1 = 120; // Green
  const baseHue2 = 0;   // Red
  
  // Random rotation angle (0-360 degrees)
  const rotation = Math.random() * 360;
  
  // Apply rotation to both base hues
  const newHue1 = (baseHue1 + rotation) % 360;
  const newHue2 = (baseHue2 + rotation) % 360;
  
  // Convert HSL to RGB
  const primaryRgb = hslToRgb(newHue1, 100, 50); // Primary (green-like)
  const secondaryRgb = hslToRgb(newHue2, 100, 50); // Secondary (red-like)
  
  const primary = `rgb(${primaryRgb.r}, ${primaryRgb.g}, ${primaryRgb.b})`;
  const secondary = `rgb(${secondaryRgb.r}, ${secondaryRgb.g}, ${secondaryRgb.b})`;
  
  return {
    primary,
    secondary,
    primaryRgb: `${primaryRgb.r}, ${primaryRgb.g}, ${primaryRgb.b}`,
    secondaryRgb: `${secondaryRgb.r}, ${secondaryRgb.g}, ${secondaryRgb.b}`
  };
}

export default function SnakeGame({ onClose, onUnlock }: SnakeGameProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [gameState, setGameState] = useState<"menu" | "playing" | "over" | "unlocked" | "paused">("menu");
  const [score, setScore] = useState(0);
  const [level, setLevel] = useState(1);
  const [showStats, setShowStats] = useState(false);
  
  // Dynamic color theme state
  const [themeColors, setThemeColors] = useState<{ primary: string; secondary: string; primaryRgb: string; secondaryRgb: string }>(() => 
    generateRandomTheme()
  );
  
  const stats = getSnakeStats();
  const [highScore, setHighScore] = useState(stats.highScore);
  const [averageScore, setAverageScore] = useState(getAverageScore());
  
  const gameStartTimeRef = useRef<number>(0);
  const snakeRef = useRef<Pos[]>([{ x: 10, y: 10 }]);
  const dirRef = useRef<Dir>("RIGHT");
  const nextDirRef = useRef<Dir>("RIGHT");
  const foodRef = useRef<Pos>({ x: 15, y: 10 });
  const scoreRef = useRef(0);
  const levelRef = useRef(1);
  const loopRef = useRef<number | null>(null);
  const unlockedRef = useRef(false);
  const touchStartRef = useRef<{ x: number; y: number } | null>(null);

  // Generate new theme when starting a new game
  useEffect(() => {
    if (gameState === "menu") {
      setThemeColors(generateRandomTheme());
    }
  }, [gameState]);

  // Responsive cell size — measure parent container, not window
  const [CELL, setCELL] = useState(BASE_CELL);
  useEffect(() => {
    const updateSize = () => {
      const parent = containerRef.current;
      const available = parent ? Math.min(parent.clientWidth - 48, parent.clientHeight - 200) : window.innerWidth - 48;
      const maxW = Math.min(available, 400);
      setCELL(Math.max(10, Math.floor(maxW / GRID)));
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
    unlockedRef.current = false;
    gameStartTimeRef.current = Date.now();
    setScore(0);
    setLevel(1);
    spawnFood();
  }, [spawnFood]);

  const endGame = useCallback(() => {
    const duration = Math.floor((Date.now() - gameStartTimeRef.current) / 1000);
    const finalScore = scoreRef.current;
    const finalLevel = levelRef.current;
    const wasUnlocked = unlockedRef.current;
    
    // Save game statistics
    saveSnakeGame({
      score: finalScore,
      level: finalLevel,
      duration,
      unlocked: wasUnlocked
    });
    
    // Update UI stats
    const newStats = getSnakeStats();
    setHighScore(newStats.highScore);
    setAverageScore(getAverageScore());
    
    setGameState("over");
  }, []);

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
      soundSnakeCrash();
      endGame();
      return;
    }

    // Self collision (check against body only, not current head)
    if (snake.slice(1).some(s => s.x === head.x && s.y === head.y)) {
      soundSnakeCrash();
      endGame();
      return;
    }

    snake.unshift(head);

    // Food eaten
    if (head.x === foodRef.current.x && head.y === foodRef.current.y) {
      scoreRef.current++;
      const newLevel = Math.floor(scoreRef.current / 10) + 1;
      const prevLevel = levelRef.current;
      levelRef.current = newLevel;
      soundSnakeEat();
      setScore(scoreRef.current);
      setLevel(newLevel);
      
      // Play level up sound if level increased
      if (newLevel > prevLevel) {
        soundSnakeLevelUp();
      }
      
      setHighScore(h => {
        const newHi = Math.max(h, scoreRef.current);
        return newHi;
      });
      spawnFood();

      // Check unlock condition: level 5 with 10+ points (i.e., score >= 40 since level 5 starts at score 40)
      if (newLevel >= 5 && scoreRef.current >= 10 && !unlockedRef.current) {
        unlockedRef.current = true;
        soundSnakeUnlock();
        
        // Save the successful game
        const duration = Math.floor((Date.now() - gameStartTimeRef.current) / 1000);
        saveSnakeGame({
          score: scoreRef.current,
          level: newLevel,
          duration,
          unlocked: true
        });
        
        // Update UI stats
        const newStats = getSnakeStats();
        setHighScore(newStats.highScore);
        setAverageScore(getAverageScore());
        
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
    // Ensure canvas dimensions match (in case CELL changed)
    if (canvasRef.current && (canvasRef.current.width !== W || canvasRef.current.height !== W)) {
      canvasRef.current.width = W;
      canvasRef.current.height = W;
    }

    // Background
    ctx.fillStyle = "#0a0a0a";
    ctx.fillRect(0, 0, W, W);

    // Render game elements when playing or paused
    if (gameState === "playing" || gameState === "paused") {
      // Grid lines (subtle)
      ctx.strokeStyle = "rgba(255,255,255,0.03)";
      ctx.lineWidth = 0.5;
      for (let i = 0; i <= GRID; i++) {
        ctx.beginPath(); ctx.moveTo(i * CELL, 0); ctx.lineTo(i * CELL, W); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(0, i * CELL); ctx.lineTo(W, i * CELL); ctx.stroke();
      }

      // Food with theme color
      const food = foodRef.current;
      ctx.fillStyle = themeColors.secondary;
      ctx.shadowColor = themeColors.secondary;
      ctx.shadowBlur = 8;
      ctx.fillRect(food.x * CELL + 2, food.y * CELL + 2, CELL - 4, CELL - 4);
      ctx.shadowBlur = 0;

      // Snake with theme color
      const snake = snakeRef.current;
      snake.forEach((seg, i) => {
        const isHead = i === 0;
        ctx.fillStyle = isHead ? themeColors.primary : `rgba(${themeColors.primaryRgb}, ${0.9 - i * 0.02})`;
        if (isHead) {
          ctx.shadowColor = themeColors.primary;
          ctx.shadowBlur = 12;
        }
        ctx.fillRect(seg.x * CELL + 1, seg.y * CELL + 1, CELL - 2, CELL - 2);
        ctx.shadowBlur = 0;
      });
    }

    // Scanlines handled by CSS overlay — no canvas scanlines needed
  }, [CELL, gameState, themeColors]);

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
          soundSnakeStart();
          setGameState("playing");
        }
        return;
      }
      if (gameState === "over") {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          resetGame();
          soundSnakeStart();
          setGameState("playing");
        }
        return;
      }
      if (gameState === "paused") {
        if (e.key === "p" || e.key === "P" || e.key === "Escape" || e.key === " ") {
          e.preventDefault();
          setGameState("playing");
        }
        return;
      }
      if (gameState !== "playing") return;

      // Pause
      if (e.key === "p" || e.key === "P" || e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
        setGameState("paused");
        return;
      }

      const dir = dirRef.current;
      switch (e.key) {
        case "ArrowUp": case "w": case "W":
          if (dir !== "DOWN") {
            nextDirRef.current = "UP";
            soundSnakeTurn();
          }
          break;
        case "ArrowDown": case "s": case "S":
          if (dir !== "UP") {
            nextDirRef.current = "DOWN";
            soundSnakeTurn();
          }
          break;
        case "ArrowLeft": case "a": case "A":
          if (dir !== "RIGHT") {
            nextDirRef.current = "LEFT";
            soundSnakeTurn();
          }
          break;
        case "ArrowRight": case "d": case "D":
          if (dir !== "LEFT") {
            nextDirRef.current = "RIGHT";
            soundSnakeTurn();
          }
          break;
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
        if (dx > 0 && dir !== "LEFT") {
          nextDirRef.current = "RIGHT";
          soundSnakeTurn();
        }
        else if (dx < 0 && dir !== "RIGHT") {
          nextDirRef.current = "LEFT";
          soundSnakeTurn();
        }
      } else if (Math.abs(dy) > 20) {
        if (dy > 0 && dir !== "UP") {
          nextDirRef.current = "DOWN";
          soundSnakeTurn();
        }
        else if (dy < 0 && dir !== "DOWN") {
          nextDirRef.current = "UP";
          soundSnakeTurn();
        }
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

  // Initial render for menu + re-render on pause
  useEffect(() => { render(); }, [render, gameState]);

  const W = GRID * CELL;

  return (
    <div ref={containerRef} className="absolute inset-0 z-[70] flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
      <div className="relative bg-[#0a0a0a] border-2 rounded-2xl p-4 sm:p-6 shadow-[0_0_60px_rgba(0,255,136,0.1)] max-w-full" 
             style={{ 
               borderColor: themeColors.primary,
               boxShadow: `0 0 60px rgba(${themeColors.primaryRgb}, 0.3)`
             }}>
        <button
          onClick={onClose}
          className="absolute top-2 right-2 p-1.5 text-white/20 hover:text-white/60 transition-colors"
        >
          <X size={16} />
        </button>

        {/* HUD */}
        <div className={`flex flex-wrap justify-between items-center mb-3 px-1 gap-2 ${gameState === "menu" ? "opacity-30" : ""}`} style={{ maxWidth: W }}>
          <div className="flex items-center gap-2">
            <div className="font-mono text-[9px] sm:text-[10px] uppercase tracking-widest" 
                 style={{ color: themeColors.primary }}>
              Snake Console
            </div>
            <button
              onClick={() => setShowStats(!showStats)}
              className="p-1 text-white/20 hover:text-white/60 transition-colors"
              title="View Statistics"
            >
              <BarChart3 size={12} />
            </button>
          </div>
          <div className="flex gap-2 sm:gap-3 font-mono text-[10px] sm:text-xs flex-wrap">
            <span className="text-white/40">LVL <span style={{ color: themeColors.primary }}>{level}</span></span>
            <span className="text-white/40">SC <span style={{ color: themeColors.primary }}>{score}</span></span>
            <span className="text-white/40">HI <span className="text-yellow-500">{highScore}</span></span>
          </div>
        </div>

        {/* Stats Panel */}
        {showStats && (
          <div className="mb-3 p-3 bg-black/40 border border-white/10 rounded-lg max-h-48 overflow-y-auto crt-scroll" style={{ maxWidth: W }}>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-3">
              <div className="text-center">
                <div className="text-[10px] text-white/30 font-mono uppercase">High Score</div>
                <div className="text-lg font-mono text-yellow-500">{stats.highScore}</div>
              </div>
              <div className="text-center">
                <div className="text-[10px] text-white/30 font-mono uppercase">Best Level</div>
                <div className="text-lg font-mono text-[#00ff88]">{stats.bestLevel}</div>
              </div>
              <div className="text-center">
                <div className="text-[10px] text-white/30 font-mono uppercase">Total Games</div>
                <div className="text-lg font-mono text-purple-400">{stats.totalGames}</div>
              </div>
              <div className="text-center">
                <div className="text-[10px] text-white/30 font-mono uppercase">Unlocks</div>
                <div className="text-lg font-mono text-orange-400">{stats.unlockCount}</div>
              </div>
            </div>
            
            {/* Recent Games */}
            {getRecentGames().length > 0 && (
              <div className="mb-3">
                <div className="text-[10px] text-white/30 font-mono uppercase mb-2">Recent Games</div>
                <div className="space-y-1">
                  {getRecentGames().slice(0, 5).map((game, i) => (
                    <div key={i} className="flex justify-between text-xs font-mono text-white/40">
                      <span>Score: {game.score} | Level: {game.level}</span>
                      <span>{new Date(game.timestamp).toLocaleDateString()}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            
            {/* Achievements */}
            {stats.achievements.length > 0 && (
              <div>
                <div className="text-[10px] text-white/30 font-mono uppercase mb-2">Achievements</div>
                <div className="flex flex-wrap gap-2">
                  {stats.achievements.slice(0, 6).map(achievement => {
                    const info = getAchievementInfo()[achievement];
                    return info ? (
                      <div key={achievement} className="flex items-center gap-1 px-2 py-1 bg-white/5 rounded text-xs" title={info.description}>
                        <span>{info.icon}</span>
                        <span className="text-white/60">{info.name}</span>
                      </div>
                    ) : null;
                  })}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Canvas */}
        <div className="relative mx-auto rounded-lg overflow-hidden border border-white/10" style={{ width: W, height: W }}>
          <canvas
            ref={canvasRef}
            width={W}
            height={W}
            className="block"
            style={{ imageRendering: "pixelated", width: W, height: W }}
          />

          <div
            className="pointer-events-none absolute inset-0 opacity-30"
            style={{
              backgroundImage: "linear-gradient(to bottom, rgba(255,255,255,0.06) 0%, rgba(255,255,255,0.02) 8%, rgba(0,0,0,0) 14%, rgba(0,0,0,0.18) 100%)",
              mixBlendMode: "screen",
            }}
          />

          <div
            className="pointer-events-none absolute inset-0 opacity-20"
            style={{
              backgroundImage: `radial-gradient(circle at center, rgba(${themeColors.primaryRgb}, 0.08) 0%, rgba(0,0,0,0) 62%, rgba(0,0,0,0.45) 100%)`,
            }}
          />

          <div
            className="pointer-events-none absolute inset-0 opacity-25"
            style={{
              backgroundImage: "repeating-linear-gradient(to bottom, rgba(255,255,255,0.05) 0px, rgba(255,255,255,0.05) 1px, rgba(0,0,0,0) 2px, rgba(0,0,0,0) 4px)",
              mixBlendMode: "soft-light",
            }}
          />

          <div
            className="pointer-events-none absolute inset-0 opacity-15"
            style={{
              backgroundImage: "linear-gradient(to right, rgba(255,0,0,0.08), rgba(0,255,0,0.04) 45%, rgba(0,0,255,0.08))",
              mixBlendMode: "screen",
            }}
          />

          {/* Overlays */}
          {gameState === "menu" && (
            <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/70">
              <div className="text-center mb-6">
                <div
                  className="text-3xl font-bold mb-2 animate-pulse"
                  style={{ color: themeColors.primary, textShadow: `0 0 20px ${themeColors.primary}` }}
                >
                  SNAKE CONSOLE
                </div>
                <div className="text-white/30 text-xs font-mono mb-2">A test of skill and patience</div>
                <div className="text-white/20 text-[10px] font-mono mb-4 text-center max-w-xs leading-relaxed" style={{ textShadow: "0 0 4px rgba(255,255,255,0.2)" }}>
                  Legend speaks of an ancient kasset of immense power,<br/>
                  accessible only to those who prove their mastery.<br/>
                  <span
                    className="font-semibold"
                    style={{ color: themeColors.secondary, textShadow: `0 0 8px ${themeColors.secondary}` }}
                  >
                    Reach Level 5
                  </span> to unlock its secrets.
                </div>
              </div>
              <div className="text-white/15 text-[9px] font-mono mb-6">Arrow keys, WASD, or swipe to move</div>
              <button
                onClick={() => {
                  soundSnakeStart();
                  resetGame();
                  setGameState("playing");
                }}
                className="px-6 py-2 text-black font-bold text-sm uppercase tracking-widest rounded hover:bg-white hover:scale-105 active:scale-95 transition-all duration-150"
                style={{ backgroundColor: themeColors.primary, boxShadow: `0 0 20px rgba(${themeColors.primaryRgb}, 0.3)` }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.boxShadow = `0 0 30px rgba(${themeColors.primaryRgb}, 0.5)`;
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.boxShadow = `0 0 20px rgba(${themeColors.primaryRgb}, 0.3)`;
                }}
              >
                Begin Trial
              </button>
            </div>
          )}

          {gameState === "over" && (
            <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/80">
              <div
                className="text-2xl font-bold mb-1"
                style={{ color: themeColors.secondary, textShadow: `0 0 15px ${themeColors.secondary}` }}
              >
                TRIAL FAILED
              </div>
              <div className="text-white/40 text-sm font-mono mb-1">Score: {score} | Level: {level}</div>
              <div className="text-white/20 text-[10px] font-mono mb-4 text-center max-w-xs leading-relaxed" style={{ textShadow: "0 0 4px rgba(255,255,255,0.2)" }}>
                {level < 5 ? (
                  <>
                    The ancient kasset remains locked.<br/>
                    <span
                      className="font-semibold"
                      style={{ color: themeColors.secondary, textShadow: `0 0 8px ${themeColors.secondary}` }}
                    >
                      Level 5
                    </span> is required to prove your worth.
                    <br/>
                    {5 - level} more level{5 - level > 1 ? "s" : ""} needed.
                  </>
                ) : (
                  <>
                    So close to unlocking the kasset's power!<br/>
                    Try again with renewed focus.
                  </>
                )}
              </div>
              <button
                onClick={() => {
                  soundSnakeStart();
                  resetGame();
                  setGameState("playing");
                }}
                className="px-6 py-2 text-black font-bold text-sm uppercase tracking-widest rounded hover:bg-white hover:scale-105 active:scale-95 transition-all duration-150"
                style={{ backgroundColor: themeColors.primary, boxShadow: `0 0 20px rgba(${themeColors.primaryRgb}, 0.3)` }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.boxShadow = `0 0 30px rgba(${themeColors.primaryRgb}, 0.5)`;
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.boxShadow = `0 0 20px rgba(${themeColors.primaryRgb}, 0.3)`;
                }}
              >
                Try Again
              </button>
            </div>
          )}

          {gameState === "paused" && (
            <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/60">
              <div
                className="text-2xl font-bold mb-2 animate-pulse"
                style={{ color: themeColors.primary, textShadow: `0 0 20px ${themeColors.primary}` }}
              >
                PAUSED
              </div>
              <div className="text-white/30 text-xs font-mono mb-4">Score: {score} | Level: {level}</div>
              <button
                onClick={() => setGameState("playing")}
                className="px-6 py-2 text-black font-bold text-sm uppercase tracking-widest rounded hover:bg-white hover:scale-105 active:scale-95 transition-all duration-150"
                style={{ backgroundColor: themeColors.primary, boxShadow: `0 0 20px rgba(${themeColors.primaryRgb}, 0.3)` }}
              >
                Resume
              </button>
              <div className="text-white/15 text-[9px] font-mono mt-3">P / ESC / SPACE to resume</div>
            </div>
          )}

          {gameState === "unlocked" && (
            <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/80">
              <div className="text-center mb-6">
                <div className="relative mb-4">
                  <div
                    className="text-3xl font-bold animate-pulse"
                    style={{ color: themeColors.primary, textShadow: `0 0 30px ${themeColors.primary}, 0 0 60px ${themeColors.primary}` }}
                  >
                    KASSET UNLOCKED
                  </div>
                  <div
                    className="absolute inset-0 text-3xl font-bold opacity-20 blur-sm"
                    style={{ textShadow: `0 0 40px ${themeColors.primary}` }}
                  >
                    KASSET UNLOCKED
                  </div>
                </div>
                <div className="text-white/60 text-sm font-mono mb-2">You have proven your mastery!</div>
                <div className="text-white/30 text-[10px] font-mono mb-4 max-w-xs mx-auto leading-relaxed" style={{ textShadow: "0 0 4px rgba(255,255,255,0.2)" }}>
                  The legendary kasset of immense power now belongs to you.<br/>
                  Its capabilities await in the cartridge carousel.
                </div>
              </div>
              <button
                onClick={onClose}
                className="px-6 py-2 text-black font-bold text-sm uppercase tracking-widest rounded hover:bg-white hover:scale-105 active:scale-95 transition-all duration-150"
                style={{ backgroundColor: themeColors.primary, boxShadow: `0 0 20px rgba(${themeColors.primaryRgb}, 0.3)` }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.boxShadow = `0 0 30px rgba(${themeColors.primaryRgb}, 0.5)`;
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.boxShadow = `0 0 20px rgba(${themeColors.primaryRgb}, 0.3)`;
                }}
              >
                Claim Your Reward
              </button>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="mt-3 flex justify-between items-center px-1" style={{ maxWidth: W }}>
          <div className="text-[8px] sm:text-[9px] text-white/15 font-mono">10 pts/level • P to pause</div>
          <div className="text-[8px] sm:text-[9px] text-white/15 font-mono hidden sm:block">WASD / arrows to move</div>
          <div className="text-[8px] sm:text-[9px] text-white/15 font-mono sm:hidden">swipe to move</div>
        </div>
      </div>
    </div>
  );
}
