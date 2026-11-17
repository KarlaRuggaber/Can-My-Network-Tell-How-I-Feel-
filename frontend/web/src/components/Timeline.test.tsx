import type { Day, Timeline } from "../api";
import { differences } from "./Timeline";

const tl = {
  observed: {
    params: { deviation_z: 1.5 },
    tracks: [
      { key: "quiet_start", label: "Went quiet", unit: "time", sensitive: false, risk: [1] },
      { key: "night_minutes", label: "Use at night", unit: "min", sensitive: false, risk: [1] },
      { key: "chat_sessions", label: "Chat sessions", unit: "count", sensitive: false, risk: [-1] },
    ],
  },
} as unknown as Timeline;

describe("differences", () => {
  it("words clear differences and marks the risk direction", () => {
    const d = { observed: { deviation: { quiet_start: 2.1, night_minutes: -1.8, chat_sessions: -0.4 },
      sensitive: [{ metric: "C9_F1", label: "Crisis-line domain hits", value: 3 }] } } as unknown as Day;
    expect(differences(tl, d)).toEqual([
      { text: "Went quiet later", risk: true },
      { text: "Less use at night", risk: false },
      { text: "Crisis-line domain hits", risk: true },
    ]);
  });
});
