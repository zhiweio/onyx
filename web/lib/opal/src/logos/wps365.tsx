import type { IconProps } from "@opal/types";

const SvgWps365 = ({ size, ...props }: IconProps) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    {...props}
  >
    <rect x="1" y="1" width="22" height="22" rx="5" fill="#E8442E" />
    <path
      d="m13.5 14.5l2 4l6.5-13h-7l-3 6l-3.5 7L2 5.5h7l1.5 3"
      stroke="white"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);

export default SvgWps365;
