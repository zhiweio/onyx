"use client";

import { useLayoutEffect, useRef } from "react";
import type * as React from "react";
import { useViewportPlugin } from "@embedpdf/plugin-viewport/react";

const MAX_REGISTRATION_ATTEMPTS = 300;

// Mirrors @embedpdf's useViewportRef with two race fixes: registration retries
// until the document state exists (the library hook gives up permanently when
// registerViewport throws, because documents open in a passive effect after
// layout effects run), and current metrics are reported right after
// registration so the zoom plugin can lift its viewport gate even when no
// resize follows. The plugin drops metrics for unknown documents, so
// observing before registration succeeds is safe.
export function useRegisteredViewportRef(
  documentId: string
): React.RefObject<HTMLDivElement> {
  const { plugin: viewportPlugin } = useViewportPlugin();
  const containerRef = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    if (!viewportPlugin) return;
    const container = containerRef.current;
    if (!container) return;
    const reportMetrics = () => {
      viewportPlugin.setViewportResizeMetrics(documentId, {
        width: container.offsetWidth,
        height: container.offsetHeight,
        clientWidth: container.clientWidth,
        clientHeight: container.clientHeight,
        scrollTop: container.scrollTop,
        scrollLeft: container.scrollLeft,
        scrollWidth: container.scrollWidth,
        scrollHeight: container.scrollHeight,
        clientLeft: container.clientLeft,
        clientTop: container.clientTop,
      });
    };
    const onScroll = () => {
      viewportPlugin.setViewportScrollMetrics(documentId, {
        scrollTop: container.scrollTop,
        scrollLeft: container.scrollLeft,
      });
    };
    const resizeObserver = new ResizeObserver(reportMetrics);
    container.addEventListener("scroll", onScroll);
    resizeObserver.observe(container);
    let frame = 0;
    let attempts = 0;
    let cancelled = false;
    const attach = () => {
      if (cancelled) return;
      try {
        viewportPlugin.registerViewport(documentId);
      } catch {
        // Document state appears once loading starts; retry next frame.
        if (attempts++ < MAX_REGISTRATION_ATTEMPTS) {
          frame = window.requestAnimationFrame(attach);
        }
        return;
      }
      reportMetrics();
    };
    attach();
    return () => {
      cancelled = true;
      window.cancelAnimationFrame(frame);
      resizeObserver.disconnect();
      container.removeEventListener("scroll", onScroll);
      viewportPlugin.unregisterViewport(documentId);
    };
  }, [viewportPlugin, documentId]);

  return containerRef as React.RefObject<HTMLDivElement>;
}
