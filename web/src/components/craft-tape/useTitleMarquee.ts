"use client";

import { useEffect, useMemo, useRef } from "react";

/* Overflow this small hides no meaningful tail; scrolling for it reads as an
   accidental jitter, so the title stays put. */
const MIN_TITLE_REVEAL_PX = 8;

/* Marquee travel speed: slow enough to read the text as it passes. */
const TITLE_MARQUEE_PX_PER_MS = 0.03;

function placeTitle(title: HTMLSpanElement, left: number, range: number): void {
  if (typeof title.scrollTo === "function") {
    title.scrollTo({ left, behavior: "instant" });
  } else {
    title.scrollLeft = left;
  }
  if (left > 0) title.dataset.scrolled = "";
  else delete title.dataset.scrolled;
  if (left < range) title.dataset.clipped = "";
  else delete title.dataset.clipped;
}

function restTitle(title: HTMLSpanElement): void {
  if (typeof title.scrollTo === "function") {
    title.scrollTo({ left: 0, behavior: "instant" });
  } else {
    title.scrollLeft = 0;
  }
  delete title.dataset.scrolled;
  delete title.dataset.clipped;
}

/**
 * dsh title marquee: while the row is hovered, an over-long title crawls at a
 * constant speed to its far edge, rests there, and returns in one step on
 * leave (the resting ellipsis and the narrowed cell would otherwise meet the
 * text while it travelled back). Reduced motion jumps to the far edge. The
 * 12px gradient fade masks ride the `[data-scrolled]` / `[data-clipped]`
 * hooks in globals.css.
 */
export function useTitleMarquee(
  titleRef: React.RefObject<HTMLSpanElement | null>
): {
  enter: () => void;
  leave: () => void;
} {
  const frame = useRef(0);
  useEffect(() => () => window.cancelAnimationFrame(frame.current), []);
  return useMemo(
    () => ({
      enter: (): void => {
        const element = titleRef.current;
        if (element === null) return;
        const range = element.scrollWidth - element.clientWidth;
        if (range <= MIN_TITLE_REVEAL_PX) return;
        if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
          placeTitle(element, range, range);
          return;
        }
        window.cancelAnimationFrame(frame.current);
        let previous: number | undefined;
        let position = 0;
        const step = (now: number): void => {
          position +=
            previous === undefined
              ? 0
              : (now - previous) * TITLE_MARQUEE_PX_PER_MS;
          previous = now;
          placeTitle(element, Math.min(position, range), range);
          if (position < range)
            frame.current = window.requestAnimationFrame(step);
        };
        frame.current = window.requestAnimationFrame(step);
      },
      leave: (): void => {
        window.cancelAnimationFrame(frame.current);
        const element = titleRef.current;
        if (element === null) return;
        restTitle(element);
      },
    }),
    [titleRef]
  );
}
