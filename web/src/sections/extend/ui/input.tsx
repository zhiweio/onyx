import * as React from "react";

import { cn } from "@/sections/extend/lib/utils";

const Input = React.forwardRef<HTMLInputElement, React.ComponentProps<"input">>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        type={type}
        className={cn(
          "flex h-9 w-full rounded-md border border-oklch(0.922 0 0) bg-transparent px-3 py-1 text-base shadow-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-oklch(0.145 0 0) placeholder:text-oklch(0.556 0 0) focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-oklch(0.708 0 0) disabled:cursor-not-allowed disabled:opacity-50 md:text-sm dark:border-oklch(1 0 0 / 10%) dark:border-oklch(1 0 0 / 15%) dark:file:text-oklch(0.985 0 0) dark:placeholder:text-oklch(0.708 0 0) dark:focus-visible:ring-oklch(0.556 0 0)",
          className
        )}
        ref={ref}
        {...props}
      />
    );
  }
);
Input.displayName = "Input";

export { Input };
