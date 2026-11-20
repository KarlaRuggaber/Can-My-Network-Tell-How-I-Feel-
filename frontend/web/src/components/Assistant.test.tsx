import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { api, type ChatTurn } from "../api";
import { Assistant, followUps, MORE_DETAIL, SHORTER, resetConversations } from "./Assistant";

vi.mock("../api", async (orig) => {
  const mod = await orig<typeof import("../api")>();
  return { ...mod, api: { ...mod.api, assistant: vi.fn(), ask: vi.fn() } };
});

const calls = () => vi.mocked(api.ask).mock.calls.map((c) => c[1] as ChatTurn[]);

async function renderAnswered(props: Partial<Parameters<typeof Assistant>[0]> = {}) {
  vi.mocked(api.assistant).mockResolvedValue({ enabled: true, notice: "" } as never);
  vi.mocked(api.ask).mockImplementation(async (_id, _m, _f, onText) => { onText("Fewer quiet hours on **Tue**."); });
  render(<Assistant open onToggle={() => undefined} profileId="p1" person={false} focus="overview" {...props} />);
  const first = await screen.findByRole("button", { name: "What drives the recent likelihoods?" });
  await act(async () => { fireEvent.click(first); });
  await screen.findByRole("button", { name: "Make this answer shorter" });
}

describe("Assistant answer controls", () => {
  beforeEach(() => { vi.clearAllMocks(); resetConversations(); });

  it("sends Shorter and More detail as follow-up messages with the conversation so far", async () => {
    await renderAnswered();
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Make this answer shorter" })); });
    const more = await screen.findByRole("button", { name: "Explain this answer in more detail" });
    await act(async () => { fireEvent.click(more); });
    const [, second, third] = calls();
    expect(second.map((t) => t.content)).toEqual(["What drives the recent likelihoods?", "Fewer quiet hours on **Tue**.", SHORTER]);
    expect(third[third.length - 1]).toEqual({ role: "user", content: MORE_DETAIL });
    expect(SHORTER).toBe("Shorter");
    expect(MORE_DETAIL).toBe("More detail");
  });

  it("offers follow-ups from the current focus and sends them", async () => {
    await renderAnswered({ focusInfo: { day: "2025-11-04", criterion: { key: "C4", name: "Sleep" } } });
    const group = screen.getByRole("group", { name: "Follow-up questions" });
    const pills = Array.from(group.querySelectorAll("button")).map((b) => b.textContent);
    expect(pills).toEqual(["What else stood out on 04/11?", "Which metric drives C4 most?", "How reliable is C4 from network data?"]);
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Which metric drives C4 most?" })); });
    await waitFor(() => expect(calls()).toHaveLength(2));
    expect(calls()[1].at(-1)!.content).toBe("Which metric drives C4 most?");
  });

  it("hides the controls while an answer is still streaming", async () => {
    vi.mocked(api.assistant).mockResolvedValue({ enabled: true, notice: "" } as never);
    vi.mocked(api.ask).mockImplementation(() => new Promise(() => undefined));
    render(<Assistant open onToggle={() => undefined} profileId="p1" person focus={null} />);
    const pill = await screen.findByRole("button", { name: "Which days stood out?" });
    await act(async () => { fireEvent.click(pill); });
    expect(screen.queryByRole("button", { name: "Make this answer shorter" })).toBeNull();
  });
});

describe("followUps", () => {
  it("gives 2–3 short questions, flag first, without clinical terms for the person", () => {
    expect(followUps(true, { flag: "quiet_short", day: "2025-11-04" }))
      .toEqual(["Has this happened before?", "How did 04/11 compare with my usual days?", "What changed compared with my usual weeks?"]);
    expect(followUps(false)).toEqual(["Recent period vs. baseline?", "Which flags need a look first?"]);
    for (const f of [{}, { day: "2025-11-04" }, { criterion: { key: "C4", name: "Sleep" } }]) {
      const out = followUps(true, f);
      expect(out.length).toBeGreaterThanOrEqual(2);
      expect(out.length).toBeLessThanOrEqual(3);
      expect(out.join(" ")).not.toMatch(/C\d|criterion|likelihood/);
    }
  });
});

describe("Assistant across tabs", () => {
  beforeEach(() => { vi.clearAllMocks(); resetConversations(); });

  it("takes an Explain request once and keeps the conversation when another tab mounts its panel", async () => {
    vi.mocked(api.assistant).mockResolvedValue({ enabled: true, notice: "" } as never);
    vi.mocked(api.ask).mockImplementation(async (_id, _m, _f, onText) => { onText("Two late nights."); });
    const handled = vi.fn();
    const toggle = vi.fn();
    const req = { id: 1, question: "Why later nights?", focus: "flag later_nights" };
    const first = render(<Assistant request={req} onRequestHandled={handled} open={false} onToggle={toggle}
      profileId="p1" person={false} focus="overview" />);
    await screen.findByText("Two late nights.");
    expect(handled).toHaveBeenCalledTimes(1);
    expect(toggle).toHaveBeenCalledWith(true);
    first.unmount();
    // the page cleared the request after it was handled; the next tab mounts a fresh panel
    toggle.mockClear();
    render(<Assistant request={null} onRequestHandled={handled} open={false} onToggle={toggle}
      profileId="p1" person={false} focus="timeline" />);
    expect(await screen.findByText("Two late nights.")).toBeTruthy();   // conversation kept
    expect(api.ask).toHaveBeenCalledTimes(1);                            // not asked again
    expect(toggle).not.toHaveBeenCalled();                               // not reopened
  });
});
