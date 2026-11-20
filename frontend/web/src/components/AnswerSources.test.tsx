import { fireEvent, render, screen } from "@testing-library/react";
import type { AnswerSources as Sources, SourceItem } from "../api";
import { AnswerSources, valueRow } from "./AnswerSources";

const item = (o: Partial<SourceItem>): SourceItem => ({
  kind: "metric", id: "quiet_hours", name: "Quiet window", icon: "moon", unit: "h", values: [], usual: null, detail: null,
  code: null, days: [], ...o,
});
const QUIET = item({ values: [{ day: "2025-10-31", text: "5.2 h" }], usual: "6.8 to 7.6 h", days: ["2025-10-31"] });
const SLEEP = item({ kind: "criterion", id: "C4", name: "Sleep (C4)", icon: null, unit: null, code: "C4",
  values: [{ day: "2025-10-31", text: "L 0.62" }], detail: "Recent: present", days: ["2025-10-31"] });
const DAY = item({ kind: "day", id: "2025-10-31", name: "2025-10-31", icon: null, unit: null, detail: "Fri, Recent", days: ["2025-10-31"] });
const sources = (items: SourceItem[], o: Partial<Sources> = {}): Sources => ({ items, fallback: false, no_data: false, ...o });

describe("AnswerSources", () => {
  it("is one collapsed line of chips; values show on request", () => {
    render(<AnswerSources sources={sources([QUIET, SLEEP, DAY])} onJump={() => undefined} />);
    expect(screen.getByText("Based on:")).toBeTruthy();
    for (const name of [/Quiet window/, /Sleep \(C4\)/, /31\/10/]) expect(screen.getByRole("button", { name })).toBeTruthy();
    expect(screen.queryByText(/usual 6.8 to 7.6 h/)).toBeNull();                       // collapsed by default
    const toggle = screen.getByRole("button", { name: "Show values" });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(toggle);
    expect(screen.getByText("Quiet window; 5.2 h on 31/10; usual 6.8 to 7.6 h")).toBeTruthy();
    expect(screen.getByText("Sleep (C4); L 0.62 on 31/10; Recent: present")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Hide values" }).getAttribute("aria-expanded")).toBe("true");
  });

  it("a chip click reports the item (the page jumps)", () => {
    const jump = vi.fn();
    render(<AnswerSources sources={sources([QUIET, DAY])} onJump={jump} />);
    fireEvent.click(screen.getByRole("button", { name: /31\/10/ }));
    expect(jump).toHaveBeenCalledWith(DAY);
    fireEvent.click(screen.getByRole("button", { name: /Quiet window/ }));
    expect(jump).toHaveBeenLastCalledWith(QUIET);
  });

  it("chips of items without a place to go are plain labels", () => {
    const area = item({ kind: "criterion", id: "Sleep", name: "Sleep", icon: null, unit: null });
    render(<AnswerSources sources={sources([area])} onJump={() => undefined} />);
    expect(screen.queryByRole("button", { name: /Sleep/ })).toBeNull();
    expect(screen.getByText("Sleep")).toBeTruthy();
  });

  it("marks the fallback, and says when no data of the person was used", () => {
    const { unmount } = render(<AnswerSources sources={sources([DAY], { fallback: true })} />);
    expect(screen.getByText("Based on: the current view")).toBeTruthy();
    expect(screen.getByText("fallback")).toBeTruthy();
    unmount();
    render(<AnswerSources sources={sources([], { no_data: true })} />);
    expect(screen.getByText("Based on: how the portal works, no data of this person")).toBeTruthy();
  });

  it("shows nothing for an empty non-fallback record, and never a middle dot", () => {
    const { container } = render(<AnswerSources sources={sources([])} />);
    expect(container.textContent).toBe("");
    expect(valueRow(QUIET)).not.toContain("·");
  });

  it("a flag row lists its days; a person's area row has only its name", () => {
    const flag = item({ kind: "flag", id: "later_nights", name: "Later nights", icon: null, unit: null, detail: "2 of the last 7 days",
      values: [{ day: "2025-10-30", text: "" }, { day: "2025-10-31", text: "" }], days: ["2025-10-30", "2025-10-31"] });
    expect(valueRow(flag)).toBe("Later nights; 30/10, 31/10; 2 of the last 7 days");
    expect(valueRow(item({ kind: "criterion", id: "Sleep", name: "Sleep", icon: null, unit: null }))).toBe("Sleep");
  });
});
