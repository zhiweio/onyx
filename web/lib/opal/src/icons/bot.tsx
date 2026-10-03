import type { IconProps } from "@opal/types";

const SvgBot = ({ size, ...props }: IconProps) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    stroke="currentColor"
    {...props}
  >
    <path d="M12 8V4H8" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
    <rect
      width="16"
      height="12"
      x="4"
      y="8"
      rx="2"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
    />
    <path d="M2 14h2" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
    <path d="M20 14h2" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
    <path d="M15 13v2" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
    <path d="M9 13v2" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);
export default SvgBot;
