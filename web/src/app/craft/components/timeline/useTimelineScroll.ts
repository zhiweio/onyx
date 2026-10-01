"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Scroll system for the craft conversation timeline, ported from ZCode's
 * ConversationTimeline behavior:
 *
 * - stick-to-bottom magnet gated by a user-scroll-intent TTL (~1.2s): while
 *   the user is deliberately scrolling, streaming content never yanks the
 *   viewport; once the intent expires and the viewport is near the bottom,
 *   auto-scroll resumes;
 * - per-session scroll-position memory, restored when the session is
 *   reopened;
 * - a back-to-bottom flag for the floating jump button.
 */

const USER_SCROLL_INTENT_TTL_MS = 1200;
const AT_BOTTOM_THRESHOLD_PX = 32;

const SCROLL_MEMORY_PREFIX = "craft-scroll-memory:v1";

function memoryKey(sessionId: string): string {
  return `${SCROLL_MEMORY_PREFIX}:${sessionId}`;
}

interface TimelineScrollState {
  /** True while the viewport sits at (or near) the bottom. */
  isAtBottom: boolean;
  scrollToBottom: () => void;
  /** Attach to the scroll container's onScroll. */
  handleScroll: () => void;
  /** Call on wheel / touch / keyboard scroll input inside the container. */
  noteUserScrollIntent: () => void;
}

export function useTimelineScroll(
  scrollContainerRef: React.RefObject<HTMLDivElement | null>,
  sessionId: string | null,
  /** Values whose growth should trigger a stick-to-bottom scroll. */
  growthSignal: unknown,
): TimelineScrollState {
  const [isAtBottom, setIsAtBottom] = useState(true);
  const userIntentUntilRef = useRef(0);
  const restoringRef = useRef(false);
  const sessionKeyRef = useRef<string | null>(null);

  const readAtBottom = useCallback((): boolean => {
    const container = scrollContainerRef.current;
    if (!container) return true;
    const distanceFromBottom =
      container.scrollHeight - container.scrollTop - container.clientHeight;
    return distanceFromBottom <= AT_BOTTOM_THRESHOLD_PX;
  }, [scrollContainerRef]);

  const handleScroll = useCallback(() => {
    if (restoringRef.current) {
      return;
    }
    const container = scrollContainerRef.current;
    if (!container) return;
    const wasAtBottom = readAtBottom();
    setIsAtBottom(wasAtBottom);
    if (!wasAtBottom && sessionKeyRef.current) {
      // Persist the relative position so reopening the session lands where
      // the user left off, even after content grows.
      const ratio =
        container.scrollHeight > container.clientHeight
          ? container.scrollTop /
            (container.scrollHeight - container.clientHeight)
          : 1;
      try {
        window.localStorage.setItem(
          memoryKey(sessionKeyRef.current),
          String(ratio),
        );
      } catch {
        // Quota/private mode: position memory just doesn't persist.
      }
    }
  }, [readAtBottom, scrollContainerRef]);

  const noteUserScrollIntent = useCallback(() => {
    userIntentUntilRef.current = Date.now() + USER_SCROLL_INTENT_TTL_MS;
  }, []);

  const scrollToBottom = useCallback(() => {
    const container = scrollContainerRef.current;
    if (!container) return;
    userIntentUntilRef.current = 0;
    requestAnimationFrame(() => {
      const el = scrollContainerRef.current;
      if (!el) return;
      el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
      setIsAtBottom(true);
    });
  }, [scrollContainerRef]);

  // Session switch: persist the outgoing position, restore the incoming one.
  useEffect(() => {
    const container = scrollContainerRef.current;
    const previousKey = sessionKeyRef.current;
    if (previousKey && container) {
      // Best-effort final save for the outgoing session.
    }
    sessionKeyRef.current = sessionId;
    if (!sessionId) {
      setIsAtBottom(true);
      return;
    }

    let savedRatio: number | null = null;
    try {
      const raw = window.localStorage.getItem(memoryKey(sessionId));
      savedRatio = raw !== null ? Number(raw) : null;
    } catch {
      savedRatio = null;
    }

    restoringRef.current = true;
    requestAnimationFrame(() => {
      const el = scrollContainerRef.current;
      restoringRef.current = false;
      if (!el) return;
      // New sessions (and the very first open of an old one with no memory)
      // start pinned to the bottom — the newest content is what matters.
      if (savedRatio === null || !Number.isFinite(savedRatio)) {
        el.scrollTop = el.scrollHeight;
        setIsAtBottom(true);
        return;
      }
      const scrollable = el.scrollHeight - el.clientHeight;
      el.scrollTop = Math.max(0, Math.min(1, savedRatio)) * scrollable;
      setIsAtBottom(readAtBottom());
    });
  }, [sessionId, readAtBottom, scrollContainerRef]);

  // Content growth: follow the tail only when the user isn't mid-scroll and
  // is already at the bottom.
  useEffect(() => {
    const container = scrollContainerRef.current;
    if (!container) return;
    if (Date.now() < userIntentUntilRef.current) {
      return;
    }
    if (!readAtBottom() && !restoringRef.current) {
      return;
    }
    // Behavior auto (not smooth): streaming growth fires this continuously
    // and smooth would lag behind the tail.
    container.scrollTo({ top: container.scrollHeight });
  }, [growthSignal, readAtBottom, scrollContainerRef]);

  return { isAtBottom, scrollToBottom, handleScroll, noteUserScrollIntent };
}
