import {
  buildInlineRows,
  computeDiff,
  collapseUnchanged,
  wordSegments,
} from "@/app/craft/components/tool-cards/DiffBody";

describe("ZCode inline diff engine", () => {
  it("pairs a removed+added line into ONE modified row with word segments", () => {
    const diff = computeDiff("const a = 1;\n", "const a = 2;\n");
    const rows = buildInlineRows(diff).filter((r) => r.kind === "modified");

    // Both files end with a newline, so the trailing "" pairs as unchanged;
    // the assertion targets the modified row itself.
    expect(rows).toHaveLength(1);
    expect(rows[0]!.oldLineNum).toBe(1);
    expect(rows[0]!.newLineNum).toBe(1);
    const segs = rows[0]!.segments!;
    // Old 1 struck through, new 2 added — on the same row.
    expect(segs).toContainEqual({ t: "del", s: "1" });
    expect(segs).toContainEqual({ t: "add", s: "2" });
    expect(segs.some((s) => s.t === "same" && s.s.includes("const a = "))).toBe(
      true
    );
  });

  it("keeps pure additions and removals as their own rows", () => {
    const diff = computeDiff("keep\n", "keep\nadded\n");
    const rows = buildInlineRows(collapseUnchanged(diff, () => "", 3));
    const kinds = rows.map((r) => r.kind).filter((k) => k !== "unchanged");
    expect(kinds).toEqual(["added"]);
    const added = rows.find((r) => r.kind === "added");
    expect(added!.content).toBe("added");
  });

  it("word diff keeps shared tokens as same and splits the rest", () => {
    const segs = wordSegments("foo.bar = old_value", "foo.bar = new_value");
    expect(segs.some((s) => s.t === "same" && s.s.includes("foo.bar"))).toBe(
      true
    );
    expect(segs.some((s) => s.t === "del" && s.s.includes("old"))).toBe(true);
    expect(segs.some((s) => s.t === "add" && s.s.includes("new"))).toBe(true);
  });
});
