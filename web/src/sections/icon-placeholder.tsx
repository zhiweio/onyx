"use client";

import * as Lucide from "lucide-react";
import type { LucideIcon } from "lucide-react";

export type IconPlaceholderProps = {
  lucide: string;
  tabler?: string;
  hugeicons?: string;
  phosphor?: string;
  remixicon?: string;
} & React.ComponentProps<"svg">;

export function IconPlaceholder({
  lucide,
  tabler: _tabler,
  hugeicons: _hugeicons,
  phosphor: _phosphor,
  remixicon: _remixicon,
  ...rest
}: IconPlaceholderProps) {
  const icons = Lucide as unknown as Record<string, LucideIcon>;
  const Icon = icons[lucide] ?? Lucide.File;
  return <Icon {...rest} />;
}
