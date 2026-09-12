"use client";

import * as React from "react";
import * as TogglePrimitive from "@radix-ui/react-toggle";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/sections/extend/lib/utils";

const toggleVariants = cva(
  "inline-flex items-center justify-center gap-2 rounded-md text-sm font-medium transition-colors hover:bg-oklch(0.97 0 0) hover:text-oklch(0.556 0 0) focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-oklch(0.708 0 0) disabled:pointer-events-none disabled:opacity-50 data-[state=on]:bg-oklch(0.97 0 0) data-[state=on]:text-oklch(0.205 0 0) [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0 dark:hover:bg-oklch(0.269 0 0) dark:hover:text-oklch(0.708 0 0) dark:focus-visible:ring-oklch(0.556 0 0) dark:data-[state=on]:bg-oklch(0.269 0 0) dark:data-[state=on]:text-oklch(0.985 0 0)",
  {
    variants: {
      variant: {
        default: "bg-transparent",
        outline:
          "border border-oklch(0.922 0 0) bg-transparent shadow-sm hover:bg-oklch(0.97 0 0) hover:text-oklch(0.205 0 0) dark:border-oklch(1 0 0 / 15%) dark:hover:bg-oklch(0.269 0 0) dark:hover:text-oklch(0.985 0 0)",
      },
      size: {
        default: "h-9 px-2 min-w-9",
        sm: "h-8 px-1.5 min-w-8",
        lg: "h-10 px-2.5 min-w-10",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
);

const Toggle = React.forwardRef<
  React.ElementRef<typeof TogglePrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof TogglePrimitive.Root> &
    VariantProps<typeof toggleVariants>
>(({ className, variant, size, ...props }, ref) => (
  <TogglePrimitive.Root
    ref={ref}
    className={cn(toggleVariants({ variant, size, className }))}
    {...props}
  />
));

Toggle.displayName = TogglePrimitive.Root.displayName;

export { Toggle, toggleVariants };
