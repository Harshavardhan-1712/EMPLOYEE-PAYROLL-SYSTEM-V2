import "@testing-library/jest-dom/vitest";
import { cleanup, configure } from "@testing-library/react";
import { cloneElement, isValidElement, type ReactElement } from "react";
import { afterEach, vi } from "vitest";

// jsdom has no layout, so ResponsiveContainer would render a 0x0 chart. Give charts a fixed size in tests.
vi.mock("recharts", async () => {
  const actual = await vi.importActual<typeof import("recharts")>("recharts");
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: ReactElement }) => (isValidElement(children) ? cloneElement(children as ReactElement<{ width: number; height: number }>, { width: 600, height: 260 }) : null),
  };
});

// Pages are code-split (React.lazy), so the first render can wait on a dynamic import; give async queries headroom on slow/loaded machines.
configure({ asyncUtilTimeout: 6000 });

afterEach(() => cleanup());
