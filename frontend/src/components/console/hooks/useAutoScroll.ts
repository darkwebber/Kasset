import { useRef, useEffect } from "react";

/**
 * Manages auto-scrolling behavior for the console message area.
 * Tracks whether user is pinned to bottom and auto-scrolls during generation.
 */
export function useAutoScroll(isGenerating: boolean, streamDep: unknown, messageCount: number) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const pinnedToBottom = useRef(true);

  // Track user scroll position
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onScroll = () => {
      const { scrollTop, scrollHeight, clientHeight } = el;
      pinnedToBottom.current = scrollHeight - scrollTop - clientHeight < 80;
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, []);

  // Auto-scroll — only when pinned to bottom AND actively generating
  useEffect(() => {
    if (scrollRef.current && pinnedToBottom.current && isGenerating) {
      requestAnimationFrame(() => {
        if (scrollRef.current && pinnedToBottom.current) {
          scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
      });
    }
  }, [streamDep, isGenerating]);

  // Scroll once when new messages arrive (user send / finalize)
  useEffect(() => {
    if (scrollRef.current && pinnedToBottom.current) {
      requestAnimationFrame(() => {
        if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
      });
    }
  }, [messageCount]);

  // Pin to bottom when generation starts
  useEffect(() => {
    if (isGenerating) {
      pinnedToBottom.current = true;
    }
  }, [isGenerating]);

  return { scrollRef, pinnedToBottom };
}
