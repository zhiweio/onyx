import type { IconProps } from "@opal/types";

/**
 * LobeHub MiniMax color PNG.
 * https://lobehub.com/icons/minimax
 * https://raw.githubusercontent.com/lobehub/lobe-icons/refs/heads/master/packages/static-png/light/minimax-color.png
 */
const SvgMinimax = ({ size, ...props }: IconProps) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    {...props}
  >
    <image href="/MiniMax.png" width="24" height="24" />
  </svg>
);

export default SvgMinimax;
