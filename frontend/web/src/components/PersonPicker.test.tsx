import { fireEvent, render, screen, within } from "@testing-library/react";
import type { ProfileListItem } from "../api";
import { filterPeople, PersonPicker, sortByAttention } from "./PersonPicker";

const FIRST = ["Anna", "Ben", "Chiara", "David", "Elif", "Fabio", "Gülsen", "Hannes", "Ines", "Jonas"];
const LAST = ["Meier", "Keller", "Huber", "Weber", "Schneider", "Müller", "Brunner", "Frei", "Baumann", "Zürcher"];

/** n generated people; every 7th has new flags, every 50th the alert. */
function people(n: number, withAttention = true): ProfileListItem[] {
  return Array.from({ length: n }, (_, i) => ({
    id: `p${String(i).padStart(3, "0")}`,
    name: `${FIRST[i % 10]} ${LAST[Math.floor(i / 10) % 10]} ${i}`,
    condition: "", source: "gateway", scripted: false, first_day: null, last_day: null, n_days: 30,
    config: { id: `p${i}`, name: "", source: "gateway", all_devices: false, devices: [{ ip: "10.0.0.2", label: "phone" }],
      baseline_first: null, baseline_last: null, persona: null, view_key: "", reference: null, reference_mode: "none" },
    ...(withAttention ? { attention: { flags: i % 7 === 0 ? (i % 3) + 1 : 0, alert: i % 50 === 25 } } : {}),
  }));
}

const open = () => fireEvent.click(screen.getByRole("button", { name: /person/i }));

describe("PersonPicker", () => {
  it("searches 300 people by name, ignoring accents and case", () => {
    const list = people(300);
    expect(filterPeople(list, "gulsen")).toHaveLength(30);
    expect(filterPeople(list, "GÜLSEN zürcher")).toHaveLength(3);
    expect(filterPeople(list, "  ")).toHaveLength(300);

    render(<PersonPicker profiles={list} value="p000" onChange={() => undefined} />);
    open();
    expect(screen.getAllByRole("option")).toHaveLength(300);
    fireEvent.change(screen.getByRole("combobox", { name: "Search people" }), { target: { value: "elif frei 174" } });
    const opts = screen.getAllByRole("option");
    expect(opts).toHaveLength(1);
    expect(opts[0]!.textContent).toContain("Elif Frei 174");
    expect(screen.getByText("1 of 300 people", { exact: false })).toBeTruthy();
  });

  it("works with the keyboard: type to open, arrows, Enter selects, Escape closes", () => {
    const onChange = vi.fn();
    render(<PersonPicker profiles={people(300, false)} value="p000" onChange={onChange} />);
    const trigger = screen.getByRole("button", { name: /person/i });
    fireEvent.keyDown(trigger, { key: "j" });                 // typing on the button starts a search
    const input = screen.getByRole("combobox", { name: "Search people" }) as HTMLInputElement;
    expect(input.value).toBe("j");
    fireEvent.change(input, { target: { value: "jonas" } });
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "ArrowUp" });
    const active = input.getAttribute("aria-activedescendant")!;
    expect(document.getElementById(active)!.textContent).toContain("Jonas Keller 19");
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onChange).toHaveBeenCalledWith("p019");
    expect(screen.queryByRole("listbox")).toBeNull();

    fireEvent.keyDown(trigger, { key: "ArrowDown" });
    expect(screen.getByRole("listbox")).toBeTruthy();
    fireEvent.keyDown(screen.getByRole("combobox"), { key: "Escape" });
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(onChange).toHaveBeenCalledTimes(1);
  });

  it("shows new flags and the alert per person, flagged people first", () => {
    const list = people(300);
    const sorted = sortByAttention(list);
    expect(sorted.slice(0, 6).every((p) => p.attention!.alert)).toBe(true);
    expect(sorted[6].attention!.flags).toBe(3);

    render(<PersonPicker profiles={list} value="p025" onChange={() => undefined} />);
    // the selected person (alert, no new flags) carries the alert icon on the button itself
    const trigger = screen.getByRole("button", { name: /person/i });
    expect(within(trigger).getByRole("img", { name: "Crisis or self-harm sites" })).toBeTruthy();
    open();
    const first = screen.getAllByRole("option")[0];
    expect(within(first).getByRole("img", { name: "Crisis or self-harm sites" })).toBeTruthy();
    const flagged = screen.getAllByRole("option").find((o) => o.textContent!.includes("Anna Meier 0"))!;
    expect(flagged!.textContent).toContain("1 new");
    expect(within(flagged).queryByRole("img")).toBeNull();

    fireEvent.click(screen.getByLabelText(/only people with new flags or alerts/i));
    const n = list.filter((p) => p.attention!.alert || p.attention!.flags > 0).length;
    expect(screen.getAllByRole("option")).toHaveLength(n);
  });

  it("hides the marker while the backend sends no attention", () => {
    render(<PersonPicker profiles={people(5, false)} value="p000" onChange={() => undefined} />);
    open();
    expect(screen.queryByText(/new$/)).toBeNull();
    expect(screen.queryByRole("img")).toBeNull();
    expect(screen.queryByLabelText(/only people with/i)).toBeNull();
  });
});
