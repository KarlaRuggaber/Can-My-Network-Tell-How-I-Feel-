import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import type { Routine } from "../api";
import { defaultRoutine, RoutineForm } from "./RoutineForm";

function Harness({ onChange }: { onChange: (r: Routine) => void }) {
  const [r, setR] = useState(defaultRoutine());
  return <RoutineForm profileId="p" value={r} person assistant={false} sections={["week", "times"]}
    onChange={(x) => { setR(x); onChange(x); }} />;
}

describe("RoutineForm week and times", () => {
  it("sets a day type with one click per day and shows the times as one row each", () => {
    const seen: Routine[] = [];
    render(<Harness onChange={(r) => seen.push(r)} />);
    expect(screen.getByRole("radio", { name: "Mon: Away" }).getAttribute("aria-checked")).toBe("true");
    fireEvent.click(screen.getByRole("radio", { name: "Wed: At home" }));
    expect(seen.at(-1)!.week.wed).toBe("home");
    expect(screen.getByRole("radio", { name: "Wed: Away" }).getAttribute("aria-checked")).toBe("false");

    // one row per time: school/work day and free day side by side
    expect(screen.getByLabelText("Wake up on school or work days")).toBeTruthy();
    expect(screen.getByLabelText("Wake up on free days")).toBeTruthy();
    expect(screen.getByLabelText("Back home on away days")).toBeTruthy();

    // no away day: leave/back home times are hidden
    fireEvent.click(screen.getByRole("button", { name: "Every day free" }));
    expect(Object.values(seen.at(-1)!.week).every((t) => t === "free")).toBe(true);
    expect(screen.queryByLabelText("Back home on away days")).toBeNull();
  });
});
