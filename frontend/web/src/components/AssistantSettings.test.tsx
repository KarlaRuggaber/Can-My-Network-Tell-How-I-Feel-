import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { AssistantSettings } from "./AssistantSettings";

const providers = [
  { id: "anthropic", label: "Anthropic (Claude)", default_model: "claude-sonnet-5-5" },
  { id: "local", label: "Local model (OpenAI-compatible endpoint)", default_model: "qwen2.5:3b",
    default_base_url: "http://127.0.0.1:11434/v1" },
];
const claude = {
  enabled: true, provider: "anthropic", model: "claude-sonnet-5-5", default_model: "claude-sonnet-5-5",
  has_key: true, has_claude_key: true, base_url: "http://127.0.0.1:11434/v1", providers, notice: "",
};

describe("AssistantSettings", () => {
  let calls: { url: string; init?: RequestInit }[];

  beforeEach(() => {
    calls = [];
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init });
      if (url === "/api/assistant/check")
        return new Response(JSON.stringify({ ok: true, message: "Reached the endpoint; it serves qwen2.5:3b.", models: [] }));
      if (init?.method === "PUT") {
        const b = JSON.parse(String(init.body));
        return new Response(JSON.stringify({ ...claude, ...b, has_key: true, default_model: "qwen2.5:3b" }));
      }
      return new Response(JSON.stringify(claude));
    }));
  });
  afterEach(() => { vi.unstubAllGlobals(); });

  it("switches to a local endpoint, checks it and saves provider, URL and model", async () => {
    render(<AssistantSettings />);
    const local = await screen.findByRole("radio", { name: "Local model" });
    expect(screen.getByRole("radio", { name: "Anthropic (Claude)" }).getAttribute("aria-checked")).toBe("true");
    expect(screen.getByText(/sent to Anthropic's Claude/)).toBeTruthy();
    fireEvent.click(local);

    expect(screen.queryByLabelText(/Claude API key/)).toBeNull();          // no key field for the local model
    const url = screen.getByLabelText(/Endpoint/) as HTMLInputElement;
    const model = screen.getByLabelText(/Model name/) as HTMLInputElement;
    expect(url.value).toBe("http://127.0.0.1:11434/v1");
    expect(model.value).toBe("qwen2.5:3b");
    expect(screen.getByText(/stay on the team's own computers/)).toBeTruthy();
    fireEvent.change(url, { target: { value: "http://karla-laptop:11434/v1" } });

    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Check connection" })); });
    expect(await screen.findByText(/it serves qwen2.5:3b/)).toBeTruthy();
    expect(JSON.parse(String(calls.at(-1)!.init!.body))).toEqual({ base_url: "http://karla-laptop:11434/v1", model: "qwen2.5:3b" });

    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Save" })); });
    const put = calls.find((c) => c.init?.method === "PUT")!;
    expect(JSON.parse(String(put.init!.body))).toEqual({
      enabled: true, model: "qwen2.5:3b", provider: "local", api_key: null, base_url: "http://karla-laptop:11434/v1", fallback: false,
    });
    await waitFor(() => expect(screen.getByText("Saved.")).toBeTruthy());
  });

  it("keeps the Claude key unless it is removed", async () => {
    render(<AssistantSettings />);
    expect(await screen.findByText("stored")).toBeTruthy();
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Save" })); });
    const put = calls.find((c) => c.init?.method === "PUT")!;
    expect(JSON.parse(String(put.init!.body))).toMatchObject({ provider: "anthropic", api_key: null, base_url: null });
  });
});
