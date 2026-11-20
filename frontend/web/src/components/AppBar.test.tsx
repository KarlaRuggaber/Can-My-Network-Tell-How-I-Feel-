import { fireEvent, render, screen, within } from "@testing-library/react";
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
      myWeek={false} onToggleMyWeek={() => undefined} onLogout={() => undefined}
      thesis="A thesis" {...over} />
  );
}

// Both tab lists are in the DOM (CSS shows one per screen size; jsdom applies no CSS).
const top = () => within(document.querySelector(".appbar") as HTMLElement);
const bottom = () => within(document.querySelector(".tabbar") as HTMLElement);

describe("AppBar", () => {
  it("keeps tab semantics and moves with the arrow keys", () => {
    render(<Harness />);
    const tabs = top().getAllByRole("tab");
    expect(tabs.map((t) => t.getAttribute("aria-selected"))).toEqual(["true", "false", "false"]);
    expect(tabs[1].tabIndex).toBe(-1);
    fireEvent.keyDown(tabs[0], { key: "ArrowRight" });
    expect(top().getByRole("tab", { name: /Timeline/ }).getAttribute("aria-selected")).toBe("true");
    expect(document.activeElement).toBe(top().getByRole("tab", { name: /Timeline/ }));
    fireEvent.keyDown(document.activeElement!, { key: "ArrowLeft" });
    fireEvent.keyDown(document.activeElement!, { key: "ArrowLeft" });
    expect(top().getByRole("tab", { name: /Care plan/ }).getAttribute("aria-selected")).toBe("true");
  });

  it("gives each link its sub-label for screen readers and shows the neutral care-plan dot", () => {
    render(<Harness />);
    const t = top().getByRole("tab", { name: /Overview/ });
    const id = t.getAttribute("aria-describedby")!;
    expect(document.getElementById(id)?.textContent).toBe("what the network observed");
    expect(top().getByRole("img", { name: "incomplete" })).toBeTruthy();
  });

  it("goes to Overview from the wordmark and shows the disclaimer line", () => {
    render(<Harness />);
    fireEvent.click(top().getByRole("tab", { name: /Timeline/ }));
    fireEvent.click(screen.getByRole("button", { name: /go to Overview/ }));
    expect(top().getByRole("tab", { name: /Overview/ }).getAttribute("aria-selected")).toBe("true");
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

  it("shows the same sections as a bottom tab bar with short labels and full names", () => {
    const tabs: AppTab[] = [...TABS, { key: "about", label: "About the data", short: "About", icon: "data", sub: "what the network can see" }];
    render(<Harness tabs={tabs} />);
    const bar = bottom();
    expect(bar.getAllByRole("tab").map((t) => t.textContent)).toEqual(["Overview", "Timeline", "Care plan", "About"]);
    const about = bar.getByRole("tab", { name: "About the data" });
    fireEvent.click(about);
    expect(about.getAttribute("aria-selected")).toBe("true");
    expect(top().getByRole("tab", { name: /About the data/ }).getAttribute("aria-selected")).toBe("true");
    expect((document.querySelector(".tabbar") as HTMLElement).style.getPropertyValue("--tab-i")).toBe("3");
    fireEvent.keyDown(about, { key: "ArrowRight" });
    expect(bar.getByRole("tab", { name: "Overview" }).getAttribute("aria-selected")).toBe("true");
  });

  it("hides the bottom tab bar while settings are open", () => {
    render(<Harness settings />);
    expect(document.querySelector(".tabbar")).toBeNull();
  });
});

describe("AppBar, a disabled tab", () => {
  const LOCKED: AppTab[] = [
    { key: "overview", label: "Overview", sub: "your recent days" },
    { key: "timeline", label: "Timeline", sub: "day by day", disabled: "Available once your week is set up (My week)" },
    { key: "about", label: "About the data", sub: "what this page is based on" },
  ];
  it("is greyed out, cannot be chosen and is skipped by the arrow keys", () => {
    render(<Harness multi={false} tabs={LOCKED} />);
    const tl = top().getByRole("tab", { name: /Timeline/ });
    expect(tl.getAttribute("aria-disabled")).toBe("true");
    expect(tl.className).toContain("disabled");
    fireEvent.click(tl);
    expect(top().getByRole("tab", { name: /Overview/ }).getAttribute("aria-selected")).toBe("true");
    fireEvent.keyDown(top().getByRole("tab", { name: /Overview/ }), { key: "ArrowRight" });
    expect(top().getByRole("tab", { name: /About the data/ }).getAttribute("aria-selected")).toBe("true");
    expect(bottom().getByRole("tab", { name: /Timeline/ }).getAttribute("aria-disabled")).toBe("true");
  });
});
