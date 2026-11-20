import { api, RECORD_SEP, splitSources, type AnswerSources, type ChatTurn } from "./api";

const REC = JSON.stringify({ items: [{ kind: "day", id: "2025-10-31", name: "2025-10-31", icon: null, unit: null, values: [], usual: null, detail: null, code: null, days: [] }], fallback: false, no_data: false });

function run(chunks: string[]) {
  let text = "";
  const got: AnswerSources[] = [];
  const s = splitSources((t) => { text += t; }, (x) => got.push(x));
  chunks.forEach((c) => s.push(c));
  s.end();
  return { text, got };
}

describe("splitSources", () => {
  const whole = "Quiet on Friday." + RECORD_SEP + REC;
  it("splits the record off at every possible cut", () => {
    for (let cut = 0; cut <= whole.length; cut++) {
      const { text, got } = run([whole.slice(0, cut), whole.slice(cut)]);
      expect(text).toBe("Quiet on Friday.");
      expect(got).toHaveLength(1);
      expect(got[0].items[0].id).toBe("2025-10-31");
    }
  });
  it("never shows the record as text, even one character at a time", () => {
    const { text, got } = run([...whole]);
    expect(text).toBe("Quiet on Friday.");
    expect(text).not.toContain(RECORD_SEP);
    expect(got).toHaveLength(1);
  });
  it("a stream without a record gives text only; a cut-off record is dropped", () => {
    expect(run(["Just text."])).toEqual({ text: "Just text.", got: [] });
    expect(run(["Text" + RECORD_SEP + REC.slice(0, 20)])).toEqual({ text: "Text", got: [] });
  });
});

describe("api.ask", () => {
  afterEach(() => vi.unstubAllGlobals());
  it("streams text, hands over the sources, and sends the history without them", async () => {
    const enc = new TextEncoder();
    const parts = ["Quiet on ", "Friday.\x1e" + REC.slice(0, 30), REC.slice(30)];
    let sent: { messages: unknown[] } = { messages: [] };
    vi.stubGlobal("fetch", vi.fn(async (_u: string, init: RequestInit) => {
      sent = JSON.parse(String(init.body));
      return { ok: true, body: new ReadableStream({ start(c) { parts.forEach((p) => c.enqueue(enc.encode(p))); c.close(); } }) } as unknown as Response;
    }));
    let text = "";
    const got: AnswerSources[] = [];
    const history: ChatTurn[] = [
      { role: "user", content: "Q1" },
      { role: "assistant", content: "A1", sources: { items: [], fallback: true, no_data: false } },
      { role: "user", content: "Q2" },
    ];
    await api.ask("p1", history, null, (t) => { text += t; }, (s) => got.push(s));
    expect(text).toBe("Quiet on Friday.");
    expect(got).toHaveLength(1);
    expect(sent.messages).toEqual([{ role: "user", content: "Q1" }, { role: "assistant", content: "A1" }, { role: "user", content: "Q2" }]);
  });
});
