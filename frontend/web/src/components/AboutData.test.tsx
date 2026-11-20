import { render, screen } from "@testing-library/react";
import type { Config } from "../api";
import { CRIT_KEYS } from "../api";
import { AboutData } from "./AboutData";

const names = { C1: "Depressed mood", C2: "Anhedonia", C3: "Appetite", C4: "Sleep", C5: "Psychomotor", C6: "Fatigue", C7: "Worthlessness", C8: "Concentration", C9: "Suicidality" };
const obs = Object.fromEntries(CRIT_KEYS.map((c) => [c, { level: c === "C4" ? "good" : "partial", observes: `sees ${c}`, cannot: `not ${c}`, caveats: [], scored: c !== "C9" }]));

describe("AboutData", () => {
  it("says what the network cannot see and lists observability for C1–C9", () => {
    const cfg = { criterion_names: names, observability: obs } as unknown as Config;
    render(<AboutData cfg={cfg} focus={["C4"]} />);
    for (const t of ["No search terms", "No page content", "No message content", "Home Wi-Fi only", "Quiet is not asleep"]) {
      expect(screen.getByText(t)).toBeTruthy();
    }
    for (const c of CRIT_KEYS) expect(screen.getByText(`sees ${c}`)).toBeTruthy();
    expect(screen.getByText("Good")).toBeTruthy();
    expect(screen.getByText("not scored")).toBeTruthy();
  });

  it("still explains the data when the observability table is not available (person view)", () => {
    render(<AboutData cfg={{ criterion_names: names } as unknown as Config} />);
    expect(screen.getByText("No search terms")).toBeTruthy();
    expect(screen.queryByText("How well each criterion can be seen")).toBeNull();
  });
});
