import { cn } from "@/sections/extend/lib/utils";

function Kbd({ className, ...props }: React.ComponentProps<"kbd">) {
  return (
    <kbd
      data-slot="kbd"
      className={cn(
        "bg-oklch(0.97 0 0) text-oklch(0.556 0 0) pointer-events-none inline-flex h-5 w-fit min-w-5 select-none items-center justify-center gap-1 rounded-sm px-1 font-sans text-xs font-medium dark:bg-oklch(0.269 0 0) dark:text-oklch(0.708 0 0)",
        "[&_svg:not([class*='size-'])]:size-3",
        "[[data-slot=tooltip-content]_&]:bg-oklch(1 0 0)/20 [[data-slot=tooltip-content]_&]:text-oklch(1 0 0) dark:[[data-slot=tooltip-content]_&]:bg-oklch(1 0 0)/10 dark:[[data-slot=tooltip-content]_&]:bg-oklch(0.145 0 0)/20 dark:[[data-slot=tooltip-content]_&]:text-oklch(0.145 0 0) dark:dark:[[data-slot=tooltip-content]_&]:bg-oklch(0.145 0 0)/10",
        className
      )}
      {...props}
    />
  );
}

function KbdGroup({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <kbd
      data-slot="kbd-group"
      className={cn("inline-flex items-center gap-1", className)}
      {...props}
    />
  );
}

export { Kbd, KbdGroup };
