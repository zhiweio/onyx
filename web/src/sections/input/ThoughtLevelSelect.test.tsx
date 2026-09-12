import { render, screen, setupUser, within } from "@tests/setup/test-utils";
import ThoughtLevelSelect from "@/sections/input/ThoughtLevelSelect";

describe("ThoughtLevelSelect", () => {
  it("defaults to Max and lists Off, Low, Medium, and Max", async () => {
    const user = setupUser();
    render(
      <ThoughtLevelSelect
        value={null}
        onChange={() => undefined}
        supportsReasoning
      />
    );

    await user.click(screen.getByRole("button", { name: /max/i }));

    const menu = screen.getByRole("dialog");
    expect(within(menu).getByRole("button", { name: "Off" })).toBeInTheDocument();
    expect(within(menu).getByRole("button", { name: "Low" })).toBeInTheDocument();
    expect(
      within(menu).getByRole("button", { name: "Medium" })
    ).toBeInTheDocument();
    expect(
      within(menu).queryByRole("button", { name: "High" })
    ).not.toBeInTheDocument();
    expect(within(menu).getByRole("button", { name: "Max" })).toBeInTheDocument();
  });

  it("shows a stored High value as Max", () => {
    render(
      <ThoughtLevelSelect
        value="high"
        onChange={() => undefined}
        supportsReasoning
      />
    );

    expect(screen.getByRole("button", { name: /max/i })).toBeInTheDocument();
  });

  it("lets Max stay selectable when the admin cap is High", async () => {
    const onChange = jest.fn();
    const user = setupUser();
    render(
      <ThoughtLevelSelect
        value="medium"
        onChange={onChange}
        supportsReasoning
        effortMax="high"
      />
    );

    await user.click(screen.getByRole("button", { name: /medium/i }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Max" }));

    expect(onChange).toHaveBeenCalledWith("xhigh");
  });
});
