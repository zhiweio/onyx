import { formatJsonValue, parseArgumentsPreview } from "./callDisplay";

describe("parseArgumentsPreview", () => {
  it("parses a Python dict digest into key/value pairs", () => {
    expect(
      parseArgumentsPreview(
        "{'limit': 6, 'period': 'annual', 'thscode': '300992.SZ'}"
      )
    ).toEqual([
      { key: "limit", value: "6" },
      { key: "period", value: "annual" },
      { key: "thscode", value: "300992.SZ" },
    ]);
  });

  it("parses JSON object previews", () => {
    expect(parseArgumentsPreview('{"searchKey":"133000747390081X7"}')).toEqual([
      { key: "searchKey", value: "133000747390081X7" },
    ]);
  });

  it("keeps complete pairs when the digest is truncated", () => {
    expect(
      parseArgumentsPreview("{'limit': 6, 'period': 'annual', 'thscode': '30…")
    ).toEqual([
      { key: "limit", value: "6" },
      { key: "period", value: "annual" },
    ]);
  });

  it("returns no pairs for empty input", () => {
    expect(parseArgumentsPreview("")).toEqual([]);
    expect(parseArgumentsPreview(null)).toEqual([]);
  });
});

describe("formatJsonValue", () => {
  it("pretty-prints objects", () => {
    expect(formatJsonValue({ limit: 6, period: "annual" })).toBe(
      '{\n  "limit": 6,\n  "period": "annual"\n}'
    );
  });

  it("unfolds nested JSON strings in MCP text payloads", () => {
    const formatted = formatJsonValue({
      content: [
        {
          type: "text",
          text: '{"code":0,"message":"success"}',
        },
      ],
      isError: false,
    });

    expect(formatted).toContain('"code": 0');
    expect(formatted).toContain('"message": "success"');
    expect(formatted).not.toContain('\\"code\\"');
  });

  it("renders missing values as null", () => {
    expect(formatJsonValue(undefined)).toBe("null");
  });
});
