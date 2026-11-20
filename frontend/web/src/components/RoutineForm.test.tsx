import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { api, type Routine } from "../api";
import { defaultRoutine, mergeAnswer, RoutineForm, type MissingQuestion } from "./RoutineForm";

// The microphone needs a browser that records; here a button stands in for a finished dictation.
const SPOKEN: Record<string, string> = {
  "your week": "School Monday mornings, afternoons free.",
  "your answer": "My phone and the family iPad.",
};
vi.mock("./Dictate", async (orig) => ({
  ...(await orig<typeof import("./Dictate")>()),
  Dictate: ({ onText, label }: { onText: (t: string) => void; label?: string }) =>
    <button type="button" onClick={() => onText(SPOKEN[label ?? ""] ?? "")}>dictated {label}</button>,
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
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "dictated your week" })); });
    expect(spy).toHaveBeenCalledWith("p", "School Monday mornings, afternoons free.");
    await waitFor(() => expect(seen.at(-1)?.week.mon).toEqual({ am: "away", pm: "free" }));
    expect((screen.getAllByRole("textbox")[0] as HTMLTextAreaElement).value).toBe("School Monday mornings, afternoons free.");
    expect(await screen.findByText(/Filled in from the description/)).toBeTruthy();
    spy.mockRestore();
  });
});

const q = (id: string, fields: string[], question: string): MissingQuestion => ({ id, fields, question });

describe("RoutineForm follow-up questions", () => {
  // what the assistant makes of "School Monday mornings": no times, no devices
  const first = () => {
    const r = defaultRoutine();
    r.week.mon = { am: "away", pm: "free" };
    Object.assign(r, { away_from: null, away_to: null, bedtime: null, wake: null });
    return { ...r, missing: [
      q("sleep_free", ["bedtime_free", "wake_free"], "On weekends and other free days, when do you usually go to bed, and when do you get up?"),
      q("devices", ["devices"], "Which devices do you use at home?"),
    ] };
  };

  it("asks for what is missing one question at a time and merges each answer into the form", async () => {
    const seen: Routine[] = [];
    const answerFree = { ...defaultRoutine(), away_from: null, away_to: null, bedtime: null, wake: null,
      bedtime_free: "01:00", wake_free: "10:30", missing: [] };
    const answerDevices = { ...defaultRoutine(), away_from: null, away_to: null, bedtime: null, wake: null,
      devices: [{ name: "Phone", kind: "phone", shared: false }, { name: "iPad", kind: "tablet", shared: true }] };
    const spy = vi.spyOn(api, "suggestRoutine")
      .mockResolvedValueOnce({ routine: first() })
      .mockResolvedValueOnce({ routine: answerFree })
      .mockResolvedValueOnce({ routine: answerDevices });
    render(<Harness assistant onChange={(r) => seen.push(r)} />);
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "dictated your week" })); });

    // question 1: typed
    expect(await screen.findByText("Question 1 of 2")).toBeTruthy();
    expect(screen.queryByText(/Which devices/)).toBeNull();                 // one at a time
    const box = screen.getByLabelText(/when do you usually go to bed/);
    fireEvent.change(box, { target: { value: "around 1, up at half past ten" } });
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Answer" })); });
    expect(spy).toHaveBeenLastCalledWith("p",
      "Question: On weekends and other free days, when do you usually go to bed, and when do you get up?\nAnswer: around 1, up at half past ten");
    await waitFor(() => expect(seen.at(-1)?.bedtime_free).toBe("01:00"));
    expect(seen.at(-1)!.week.mon).toEqual({ am: "away", pm: "free" });   // the answer's default week does not overwrite
    expect(seen.at(-1)).not.toHaveProperty("missing");

    // question 2: spoken, filled in straight away
    expect(await screen.findByText("Question 2 of 2")).toBeTruthy();
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "dictated your answer" })); });
    expect(spy).toHaveBeenLastCalledWith("p", "Question: Which devices do you use at home?\nAnswer: My phone and the family iPad.");
    await waitFor(() => expect(seen.at(-1)?.devices.map((d) => d.name)).toEqual(["Phone", "iPad"]));
    const done = seen.at(-1)!;
    expect([done.bedtime_free, done.wake_free]).toEqual(["01:00", "10:30"]);
    expect(screen.queryByText(/Question \d of/)).toBeNull();
    expect(await screen.findByText(/Thank you/)).toBeTruthy();
    spy.mockRestore();
  });

  it("can always skip, one question or all the rest, and drops questions filled in by hand", async () => {
    const r = first();
    r.missing = [q("away_times", ["away_from", "away_to"], "When do you leave home, and when are you back?"), ...r.missing];
    const spy = vi.spyOn(api, "suggestRoutine").mockResolvedValue({ routine: r });
    render(<Harness assistant onChange={() => undefined} />);
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "dictated your week" })); });
    expect(await screen.findByText("Question 1 of 3")).toBeTruthy();
    // filled in by hand in the form: the question goes away
    fireEvent.change(screen.getByLabelText("Leave home on away days"), { target: { value: "07:30" } });
    fireEvent.change(screen.getByLabelText("Back home on away days"), { target: { value: "13:00" } });
    expect(await screen.findByText("Question 1 of 2")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Skip this question" }));
    expect(await screen.findByText("Question 2 of 2")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Skip the remaining questions" })).toBeNull();   // nothing after this one
    fireEvent.click(screen.getByRole("button", { name: "Skip this question" }));
    expect(screen.queryByText(/Question \d of/)).toBeNull();
    expect(spy).toHaveBeenCalledTimes(1);                                      // skipping asks the assistant nothing
    spy.mockRestore();
  });

  it("merges an answer: the asked times and the week only when asked, empty times, new devices", () => {
    const cur = { ...defaultRoutine(), bedtime: "22:00", wake_free: null, devices: [{ name: "iPhone", kind: "phone", shared: false }] };
    cur.week.wed = { am: "home", pm: "home" };
    const ans = { ...defaultRoutine(), bedtime: "23:30", wake: "06:00", wake_free: "09:00", note: "Football on Tuesdays",
      devices: [{ name: "iphone", kind: "phone", shared: false }, { name: "Laptop", kind: "laptop", shared: false }] };
    const m = mergeAnswer(cur, ans, ["wake"]);
    expect(m.week.wed).toEqual({ am: "home", pm: "home" });
    expect([m.bedtime, m.wake, m.wake_free]).toEqual(["22:00", "06:00", "09:00"]);
    expect(m.devices.map((d) => d.name)).toEqual(["iPhone", "Laptop"]);
    expect(m.note).toBe("Football on Tuesdays");
    expect(mergeAnswer(cur, ans, ["week"]).week.wed).toEqual(ans.week.wed);
  });
});
