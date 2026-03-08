"use client";

import { useState } from "react";
import { Shield, Lock, Eye, EyeOff, AlertTriangle, Wifi } from "lucide-react";
import { getApiBase, setAuthToken } from "@/lib/api";

interface NetworkAuthModalProps {
  mode: "setup" | "login";
  onAuthenticated: () => void;
}

export default function NetworkAuthModal({ mode, onAuthenticated }: NetworkAuthModalProps) {
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [lockedOut, setLockedOut] = useState(false);
  const [retryAfter, setRetryAfter] = useState(0);

  const handleSetup = async () => {
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setLoading(true);
    setError("");
    try {
      const res = await fetch(`${getApiBase()}/api/auth/setup`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });
      const data = await res.json();
      if (res.ok && data.success) {
        onAuthenticated();
      } else {
        setError(data.error || "Failed to set password.");
      }
    } catch {
      setError("Connection error. Is the server running?");
    } finally {
      setLoading(false);
    }
  };

  const handleLogin = async () => {
    if (!password) {
      setError("Please enter the password.");
      return;
    }

    setLoading(true);
    setError("");
    try {
      const res = await fetch(`${getApiBase()}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });
      const data = await res.json();
      if (res.ok && data.success && data.token) {
        setAuthToken(data.token);
        onAuthenticated();
      } else {
        setError(data.error || "Authentication failed.");
        if (data.locked_out) {
          setLockedOut(true);
          setRetryAfter(data.retry_after_seconds || 3600);
        }
      }
    } catch {
      setError("Connection error. Is the server running?");
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (mode === "setup") handleSetup();
    else handleLogin();
  };

  return (
    <div className="fixed inset-0 z-[999] flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
      <div className="w-full max-w-sm bg-[#0a0a14] border border-white/10 rounded-2xl shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="px-6 pt-6 pb-4 text-center">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 mb-4">
            {mode === "setup" ? (
              <Shield size={28} className="text-emerald-400" />
            ) : (
              <Lock size={28} className="text-emerald-400" />
            )}
          </div>
          <h2 className="text-lg font-bold text-white/90 mb-1">
            {mode === "setup" ? "Set Network Password" : "Network Access"}
          </h2>
          <p className="text-xs text-white/40 font-mono leading-relaxed">
            {mode === "setup"
              ? "Set a password to protect network access to this Kasset instance."
              : "Enter the password to access this Kasset instance."}
          </p>
        </div>

        {/* Connection indicator */}
        <div className="mx-6 mb-4 flex items-center gap-2 px-3 py-2 bg-white/[0.03] rounded-lg border border-white/5">
          <Wifi size={12} className="text-emerald-400" />
          <span className="text-[10px] font-mono text-white/40">
            Connected to {typeof window !== "undefined" ? window.location.hostname : "server"}:7861
          </span>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="px-6 pb-6 space-y-3">
          {/* Password input */}
          <div className="relative">
            <input
              type={showPassword ? "text" : "password"}
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="Password"
              autoFocus
              disabled={lockedOut}
              className="w-full px-4 py-3 pr-10 bg-white/[0.04] border border-white/10 rounded-xl text-sm text-white/90 placeholder-white/20 font-mono outline-none focus:border-emerald-500/40 transition-colors disabled:opacity-50"
            />
            <button
              type="button"
              onClick={() => setShowPassword(!showPassword)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-white/20 hover:text-white/50 transition-colors"
            >
              {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
            </button>
          </div>

          {/* Confirm password (setup only) */}
          {mode === "setup" && (
            <input
              type={showPassword ? "text" : "password"}
              value={confirmPassword}
              onChange={e => setConfirmPassword(e.target.value)}
              placeholder="Confirm password"
              className="w-full px-4 py-3 bg-white/[0.04] border border-white/10 rounded-xl text-sm text-white/90 placeholder-white/20 font-mono outline-none focus:border-emerald-500/40 transition-colors"
            />
          )}

          {/* Error */}
          {error && (
            <div className="flex items-start gap-2 px-3 py-2.5 bg-red-500/10 border border-red-500/20 rounded-lg">
              <AlertTriangle size={14} className="text-red-400 shrink-0 mt-0.5" />
              <span className="text-xs text-red-300/80 font-mono leading-relaxed">{error}</span>
            </div>
          )}

          {/* Lockout warning */}
          {lockedOut && (
            <div className="flex items-start gap-2 px-3 py-2.5 bg-amber-500/10 border border-amber-500/20 rounded-lg">
              <AlertTriangle size={14} className="text-amber-400 shrink-0 mt-0.5" />
              <span className="text-xs text-amber-300/80 font-mono leading-relaxed">
                Locked out for {Math.ceil(retryAfter / 60)} minutes due to failed attempts.
              </span>
            </div>
          )}

          {/* Submit */}
          <button
            type="submit"
            disabled={loading || lockedOut}
            className="w-full py-3 rounded-xl font-bold text-sm uppercase tracking-wider transition-all active:scale-[0.98] disabled:opacity-40 disabled:cursor-not-allowed bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/30"
          >
            {loading ? "..." : mode === "setup" ? "Set Password" : "Unlock"}
          </button>

          {mode === "setup" && (
            <p className="text-[9px] text-white/20 font-mono text-center leading-relaxed mt-2">
              This password will be required for all network clients connecting to your studio. You can change it later from the local machine.
            </p>
          )}
        </form>
      </div>
    </div>
  );
}
