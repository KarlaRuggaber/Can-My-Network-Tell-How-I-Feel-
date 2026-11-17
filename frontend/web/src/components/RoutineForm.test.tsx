import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { api, type Routine } from "../api";
import { defaultRoutine, RoutineForm } from "./RoutineForm";

// The microphone needs a browser that records; here a button stands in for a finished dictation.
vi.mock("./Dictate", async (orig) => ({
  ...(await orig<typeof import("./Dictate")>()),
  Dictate: ({ onText }: { onText: (t: string) => void }) =>
    <button type="button" onClick={() => onText("School Monday mornings, afternoons free.")}>dictated</button>,
}));

function Harness({ onChange, assistant = false }: { onChange: (r: Routine) => void; assistant?: boolean }) {
  const [r, setR] = useState(defaultRoutine());
  return <RoutineForm profileId="p" value={r} person assistant={assistant} sections={["describe", "week", "times"]}
    onChange={(x) => { setR(x); onChange(x); }} />;
}

describe("RoutineForm week and times", () => {
  it("sets the morning and the afternoon of a day with one click each", () => {
    const seen: Routine[] = [];
    render(<Harness onChange={(r) => seen.push(r)} />);
    expect(screen.getByRole("radio", { name: "Mon morning: Away" }).getAttribute("aria-checked")).toBe("true");
    fireEvent.click(screen.getByRole("radio", { name: "Wed afternoon: At home" }));
    expect(seen.at(-1)!.week.wed).toEqual({ am: "away", pm: "home" });
    expect(screen.getByRole("radio", { name: "Wed afternoon: Away" }).getAttribute("aria-checked")).toBe("false");
    expect(screen.getByRole("radio", { name: "Wed morning: Away" }).getAttribute("aria-checked")).toBe("true");

    // one row per time: school/work day and free day side by side
    expect(screen.getByLabelText("Wake up on school or work days")).toBeTruthy();
    expect(screen.getByLabelText("Wake up on free days")).toBeTruthy();
    expect(screen.getByLabelText("Back home on away days")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Mon–Fri mornings away, afternoons free" }));
    expect(seen.at(-1)!.week.fri).toEqual({ am: "away", pm: "free" });
    // no away half left: leave/back home times are hidden
    fireEvent.click(screen.getByRole("button", { name: "Every day free" }));
    expect(Object.values(seen.at(-1)!.week).every((d) => d.am === "free" && d.pm === "free")).toBe(true);
    expect(screen.queryByLabelText("Back home on away days")).toBeNull();
  });

  it("fills the form in with the assistant as soon as the dictation is there", async () => {
    const suggested = defaultRoutine();
    suggested.week.mon = { am: "away", pm: "free" };
    const spy = vi.spyOn(api, "suggestRoutine").mockResolvedValue({ routine: suggested });
    const seen: Routine[] = [];
    render(<Harness assistant onChange={(r) => seen.push(r)} />);
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "dictated" })); });
    expect(spy).toHaveBeenCalledWith("p", "School Monday mornings, afternoons free.");
    await waitFor(() => expect(seen.at(-1)?.week.mon).toEqual({ am: "away", pm: "free" }));
    expect((screen.getByRole("textbox") as HTMLTextAreaElement).value).toBe("School Monday mornings, afternoons free.");
    expect(await screen.findByText(/Filled in from the description/)).toBeTruthy();
    spy.mockRestore();
  });
});
