import { render } from "@testing-library/react";
import { ICON_NAMES, Icon } from "./Icon";

describe("Icon", () => {
  it("renders every icon as inline SVG in currentColor", () => {
    expect(ICON_NAMES).toHaveLength(21);
    for (const name of ICON_NAMES) {
      const { container, unmount } = render(<Icon name={name} />);
      const svg = container.querySelector("svg")!;
      expect(svg.getAttribute("stroke")).toBe("currentColor");
      expect(svg.getAttribute("viewBox")).toBe("0 0 24 24");
      expect(svg.getAttribute("aria-hidden")).toBe("true");
      expect(svg.children.length).toBeGreaterThan(0);
      unmount();
    }
  });

  it("gives a labelled icon an accessible name and a tooltip", () => {
    const { getByRole } = render(<Icon name="moon" label="Quiet window" />);
    const svg = getByRole("img", { name: "Quiet window" });
    expect(svg.querySelector("title")?.textContent).toBe("Quiet window");
  });

  it("makes only the alert icon red", () => {
    const { container } = render(<><Icon name="alert" /><Icon name="change" /><Icon name="clock" /></>);
    const [alert, change, clock] = Array.from(container.querySelectorAll("svg"));
    expect(alert.classList.contains("icon-alert")).toBe(true);
    expect(change.classList.contains("icon-alert")).toBe(false);
    expect(clock.getAttribute("class")).toBe("icon icon-clock");
  });
});
