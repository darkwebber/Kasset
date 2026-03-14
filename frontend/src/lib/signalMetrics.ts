/**
 * Snake Game Statistics Manager
 * Persistent game history and statistics using localStorage
 */

interface GameRecord {
  score: number;
  level: number;
  timestamp: number;
  duration: number; // seconds
  unlocked: boolean;
}

interface SnakeStats {
  highScore: number;
  totalGames: number;
  totalScore: number;
  bestLevel: number;
  totalTime: number; // seconds
  unlockCount: number;
  recentGames: GameRecord[];
  achievements: string[];
}

const STORAGE_KEY = "kasset-signal-metrics";
const MAX_RECENT_GAMES = 10;

export function getSnakeStats(): SnakeStats {
  if (typeof window === "undefined") {
    return getDefaultStats();
  }
  
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (!stored) return getDefaultStats();
    
    const parsed = JSON.parse(stored);
    return {
      ...getDefaultStats(),
      ...parsed,
      recentGames: Array.isArray(parsed.recentGames) ? parsed.recentGames.slice(0, MAX_RECENT_GAMES) : []
    };
  } catch {
    return getDefaultStats();
  }
}

function getDefaultStats(): SnakeStats {
  return {
    highScore: 0,
    totalGames: 0,
    totalScore: 0,
    bestLevel: 0,
    totalTime: 0,
    unlockCount: 0,
    recentGames: [],
    achievements: []
  };
}

export function saveSnakeGame(record: Omit<GameRecord, "timestamp"> & { timestamp?: number }): void {
  if (typeof window === "undefined") return;
  
  const stats = getSnakeStats();
  const gameRecord: GameRecord = {
    timestamp: record.timestamp || Date.now(),
    ...record
  };
  
  // Update stats
  stats.totalGames++;
  stats.totalScore += gameRecord.score;
  stats.totalTime += gameRecord.duration;
  
  if (gameRecord.score > stats.highScore) {
    stats.highScore = gameRecord.score;
  }
  
  if (gameRecord.level > stats.bestLevel) {
    stats.bestLevel = gameRecord.level;
  }
  
  if (gameRecord.unlocked) {
    stats.unlockCount++;
  }
  
  // Add to recent games (keep only last N)
  stats.recentGames.unshift(gameRecord);
  stats.recentGames = stats.recentGames.slice(0, MAX_RECENT_GAMES);
  
  // Check achievements
  checkAchievements(stats);
  
  // Save to localStorage
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(stats));
  } catch (e) {
    // Storage full, try to clear old games
    stats.recentGames = stats.recentGames.slice(0, 5);
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(stats));
    } catch {
      // Give up
    }
  }
}

function checkAchievements(stats: SnakeStats): void {
  const achievements = new Set(stats.achievements);
  
  // Score achievements
  if (stats.highScore >= 10 && !achievements.has("first_double_digit")) {
    achievements.add("first_double_digit");
  }
  if (stats.highScore >= 50 && !achievements.has("score_50")) {
    achievements.add("score_50");
  }
  if (stats.highScore >= 100 && !achievements.has("score_100")) {
    achievements.add("score_100");
  }
  
  // Level achievements
  if (stats.bestLevel >= 3 && !achievements.has("level_3")) {
    achievements.add("level_3");
  }
  if (stats.bestLevel >= 5 && !achievements.has("level_5")) {
    achievements.add("level_5");
  }
  if (stats.bestLevel >= 10 && !achievements.has("level_10")) {
    achievements.add("level_10");
  }
  
  // Games played achievements
  if (stats.totalGames >= 10 && !achievements.has("games_10")) {
    achievements.add("games_10");
  }
  if (stats.totalGames >= 50 && !achievements.has("games_50")) {
    achievements.add("games_50");
  }
  if (stats.totalGames >= 100 && !achievements.has("games_100")) {
    achievements.add("games_100");
  }
  
  // Unlock achievements
  if (stats.unlockCount >= 1 && !achievements.has("first_unlock")) {
    achievements.add("first_unlock");
  }
  if (stats.unlockCount >= 5 && !achievements.has("unlock_5")) {
    achievements.add("unlock_5");
  }
  
  stats.achievements = Array.from(achievements);
}

export function getAverageScore(): number {
  const stats = getSnakeStats();
  return stats.totalGames > 0 ? Math.round(stats.totalScore / stats.totalGames) : 0;
}

export function getAverageGameDuration(): number {
  const stats = getSnakeStats();
  return stats.totalGames > 0 ? Math.round(stats.totalTime / stats.totalGames) : 0;
}

export function getRecentGames(): GameRecord[] {
  return getSnakeStats().recentGames;
}

export function resetSnakeStats(): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Ignore
  }
}

// Achievement helpers
export function getAchievementInfo(): Record<string, { name: string; description: string; icon: string }> {
  return {
    first_double_digit: { name: "Double Digits", description: "Score 10+ points", icon: "🎯" },
    score_50: { name: "High Scorer", description: "Score 50+ points", icon: "🏆" },
    score_100: { name: "Century", description: "Score 100+ points", icon: "💯" },
    level_3: { name: "Getting Good", description: "Reach level 3", icon: "⭐" },
    level_5: { name: "Snake Master", description: "Reach level 5", icon: "👑" },
    level_10: { name: "Legendary", description: "Reach level 10", icon: "🔥" },
    games_10: { name: "Regular Player", description: "Play 10 games", icon: "🎮" },
    games_50: { name: "Dedicated", description: "Play 50 games", icon: "💪" },
    games_100: { name: "Veteran", description: "Play 100 games", icon: "🎖️" },
    first_unlock: { name: "Secret Keeper", description: "Unlock the secret", icon: "🔓" },
    unlock_5: { name: "Secret Master", description: "Unlock 5 times", icon: "🗝️" }
  };
}
