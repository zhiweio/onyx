import { cn } from "@opal/utils";
import type { IconProps } from "@opal/types";

// Parallel mark — two offset bars. Rendered in currentColor so the mark stays
// visible in both light and dark themes.
const SvgParallel = ({ size, className, ...props }: IconProps) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 56 56"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className={cn(className)}
    {...props}
  >
    <title>Parallel</title>
    <path
      d="M18.5 8L10 48H20.5L29 8H18.5ZM36.5 8L28 48H38.5L47 8H36.5Z"
      fill="currentColor"
    />
  </svg>
);

export default SvgParallel;
