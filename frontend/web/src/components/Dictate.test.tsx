import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { appendText, Dictate } from "./Dictate";

class FakeRecorder {
  static isTypeSupported = (t: string) => t === "audio/webm;codecs=opus";
  state = "inactive";
  mimeType: string;
  ondataavailable: ((e: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  constructor(public stream: { getTracks: () => { stop: () => void }[] }, opts?: { mimeType: string }) {
    this.mimeType = opts?.mimeType ?? "";
  }
  start() { this.state = "recording"; }
  stop() {
    this.state = "inactive";
    this.ondataavailable?.({ data: new Blob(["sound"], { type: this.mimeType }) });
    this.onstop?.();
  }
}

describe("Dictate", () => {
  const stopTrack = vi.fn();
  let posted: RequestInit | undefined;

  beforeEach(() => {
    vi.stubGlobal("MediaRecorder", FakeRecorder);
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia: vi.fn(async () => ({ getTracks: () => [{ stop: stopTrack }] })) },
    });
    vi.stubGlobal("fetch", vi.fn(async (_url: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        posted = init;
        return new Response(JSON.stringify({ text: "School from eight to four." }), { status: 200 });
      }
      return new Response(JSON.stringify({ available: true, max_seconds: 300 }), { status: 200 });
    }));
  });
  afterEach(() => { vi.unstubAllGlobals(); });

  it("records, sends the clip to the local service and adds the words", async () => {
    const onText = vi.fn();
    render(<Dictate onText={onText} />);
    const mic = await screen.findByRole("button", { name: /dictate/i });
    await act(async () => { fireEvent.click(mic); });
    const stop = await screen.findByRole("button", { name: /stop recording/i });
    await act(async () => { fireEvent.click(stop); });
    await waitFor(() => expect(onText).toHaveBeenCalledWith("School from eight to four."));
    expect((posted?.headers as Record<string, string>)["Content-Type"]).toBe("audio/webm;codecs=opus");
    expect(stopTrack).toHaveBeenCalled();                           // the microphone is released
    expect(await screen.findByRole("button", { name: /dictate/i })).toBeTruthy();
  });

  it("appends to what is already typed", () => {
    expect(appendText("", "hello")).toBe("hello");
    expect(appendText("I go to school. ", "On Fridays")).toBe("I go to school. On Fridays");
  });
});
