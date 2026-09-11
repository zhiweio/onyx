"use client";

import ContextUsageMeter from "@/sections/input/ContextUsageMeter";

interface ContextRingProps {
  usedTokens: number;
  contextLimit: number | null;
}

export default function ContextRing({
  usedTokens,
  contextLimit,
}: ContextRingProps) {
  return (
    <ContextUsageMeter usedTokens={usedTokens} contextLimit={contextLimit} />
  );
}
