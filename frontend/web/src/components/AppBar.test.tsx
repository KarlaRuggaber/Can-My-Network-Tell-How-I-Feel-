import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { AppBar, type AppTab } from "./AppBar";

const TABS: AppTab[] = [
  { key: "overview", label: "Overview", icon: "person", sub: "what the network observed" },
  { key: "timeline", label: "Timeline", sub: "day by day, with notes" },
  { key: "care", label: "Care plan", icon: "note", sub: "routine, devices", dot: "Care plan incomplete" },
];

function Harness(over: Partial<React.ComponentProps<typeof AppBar>> = {}) {
  const [tab, setTab] = useState("overview");
  return (
    <AppBar username="Dr Who" multi tabs={TABS} tab={tab} onTab={setTab} onHome={() => setTab("overview")}
      profiles={[]} pid={undefined} onPick={() => undefined} showPicker={false}
      settings={false} onToggleSettings={() => undefined} backLabel="Back to Anna"
      canMyWeek={false} myWeek={false} onToggleMyWeek={() => undefined} onLogout={() => undefined}
      thesis="A thesis" {...over} />
  );
}

describe("AppBar", () => {
  it("keeps tab semantics and moves with the arrow keys", () => {
    render(<Harness />);
    const tabs = screen.getAllByRole("tab");
    expect(tabs.map((t) => t.getAttribute("aria-selected"))).toEqual(["true", "false", "false"]);
    expect(tabs[1].tabIndex).toBe(-1);
    fireEvent.keyDown(tabs[0], { key: "ArrowRight" });
    expect(screen.getByRole("tab", { name: /Timeline/ }).getAttribute("aria-selected")).toBe("true");
    expect(document.activeElement).toBe(screen.getByRole("tab", { name: /Timeline/ }));
    fireEvent.keyDown(document.activeElement!, { key: "ArrowLeft" });
    fireEvent.keyDown(document.activeElement!, { key: "ArrowLeft" });
    expect(screen.getByRole("tab", { name: /Care plan/ }).getAttribute("aria-selected")).toBe("true");
  });

  it("gives each link its sub-label for screen readers and shows the neutral care-plan dot", () => {
    render(<Harness />);
    const t = screen.getByRole("tab", { name: /Overview/ });
    const id = t.getAttribute("aria-describedby")!;
    expect(document.getElementById(id)?.textContent).toBe("what the network observed");
    expect(screen.getByRole("img", { name: "incomplete" })).toBeTruthy();
  });

  it("goes to Overview from the wordmark and shows the disclaimer line", () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole("tab", { name: /Timeline/ }));
    fireEvent.click(screen.getByRole("button", { name: /go to Overview/ }));
    expect(screen.getByRole("tab", { name: /Overview/ }).getAttribute("aria-selected")).toBe("true");
    expect(screen.getByText(/Research prototype, not a diagnostic tool/)).toBeTruthy();
    expect(screen.getByText(/About: A thesis/)).toBeTruthy();
  });

  it("replaces the links with a back link while settings are open", () => {
    const back = vi.fn();
    render(<Harness settings onToggleSettings={back} />);
    expect(screen.queryAllByRole("tab")).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: /Back to Anna/ }));
    expect(back).toHaveBeenCalled();
  });

  it("offers Settings and Log out in the account menu", async () => {
    const out = vi.fn(), set = vi.fn();
    render(<Harness onLogout={out} onToggleSettings={set} />);
    const trigger = screen.getByRole("button", { name: /Account menu, signed in as Dr Who/ });
    fireEvent.keyDown(trigger, { key: "Enter" });
    fireEvent.click(await screen.findByRole("menuitem", { name: "Settings" }));
    expect(set).toHaveBeenCalled();
  });
});
