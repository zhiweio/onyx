import type { IconProps } from "@opal/types";

const SvgWandSparkles = ({ size, ...props }: IconProps) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    stroke="currentColor"
    {...props}
  >
    <path
      d="m21.64 3.64-1.28-1.28a1.21 1.21 0 0 0-1.72 0L2.36 18.64a1.21 1.21 0 0 0 0 1.72l1.28 1.28a1.2 1.2 0 0 0 1.72 0L21.64 5.36a1.2 1.2 0 0 0 0-1.72"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
    />
    <path d="m14 7 3 3" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
    <path d="M5 6v4" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
    <path d="M19 14v4" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
    <path d="M10 2v2" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
    <path d="M7 8H3" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
    <path d="M21 16h-4" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
    <path d="M11 3H9" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);
export default SvgWandSparkles;
