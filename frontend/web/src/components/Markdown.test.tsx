import { render } from "@testing-library/react";
import { Markdown } from "./Markdown";

describe("Markdown", () => {
  it("renders paragraphs, lists and bold without injecting HTML", () => {
    const { container } = render(<Markdown text={"Intro **bold** text.\n\n- **Sun 8 Nov** late\n- second\n\n<img src=x onerror=alert(1)>"} />);
    expect(container.querySelectorAll("li")).toHaveLength(2);
    expect(container.querySelector("strong")?.textContent).toBe("bold");
    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).toContain("<img src=x");
  });

  it("renders bold labels and bold phrases inside list items", () => {
    const { container } = render(<Markdown text={"Quiet on **3 of the last 7 nights**.\n\n- **Mon 16/11:** devices quiet for **5.5 h**, usual 6.6 to 10 h\n- **Tue 17/11:** usual"} />);
    const items = container.querySelectorAll("li");
    expect(items).toHaveLength(2);
    expect(items[0].querySelector("strong")?.textContent).toBe("Mon 16/11:");
    expect(items[0].querySelectorAll("strong")).toHaveLength(2);
    expect(items[0].textContent).toBe("Mon 16/11: devices quiet for 5.5 h, usual 6.6 to 10 h");
    expect(container.querySelector("p strong")?.textContent).toBe("3 of the last 7 nights");
  });

  it("repairs a day label with a missing opening ** and never shows unpaired markers", () => {
    const { container } = render(<Markdown text={"Quiet later on **most nights.\n\n- Mon 16/11:** devices quiet for 5.5 h\n- **Tue 17/11:** usual"} />);
    const items = container.querySelectorAll("li");
    expect(items[0].querySelector("strong")?.textContent).toBe("Mon 16/11:");
    expect(items[0].textContent).toBe("Mon 16/11: devices quiet for 5.5 h");
    expect(container.querySelector("p")?.textContent).toBe("Quiet later on most nights.");
    expect(container.textContent).not.toContain("**");
  });

  it("shows one bullet when the model writes a bullet character after the list marker", () => {
    const { container } = render(<Markdown text={"- • **Mon 16/11:** quiet for **5.5 h**\n- - **Tue 17/11:** usual"} />);
    const items = container.querySelectorAll("li");
    expect(items).toHaveLength(2);
    expect(items[0].textContent).toBe("Mon 16/11: quiet for 5.5 h");
    expect(items[0].querySelectorAll("strong")).toHaveLength(2);
    expect(items[1].textContent).toBe("Tue 17/11: usual");
  });
});
