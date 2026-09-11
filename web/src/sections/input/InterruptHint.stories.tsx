import type { Meta, StoryObj } from "@storybook/react-vite";
import InterruptHint from "@/sections/input/InterruptHint";

const meta: Meta<typeof InterruptHint> = {
  title: "Apps/Input Bar/Interrupt Hint",
  component: InterruptHint,
  tags: ["autodocs"],
  args: {
    interrupting: false,
  },
};

export default meta;
type Story = StoryObj<typeof InterruptHint>;

/** At rest while streaming — teaches the Esc interrupt. */
export const Default: Story = {};

/** Interrupt requested, awaiting the turn to terminate. */
export const Interrupting: Story = {
  args: {
    interrupting: true,
  },
};
