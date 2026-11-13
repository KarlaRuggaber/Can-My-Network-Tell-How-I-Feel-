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
});
