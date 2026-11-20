import { useEffect, useState } from "react";
import { ThinkingOrb } from "thinking-orbs";

/** True while the user asks the system for less motion. */
export function usePrefersReducedMotion(): boolean {
  const query = "(prefers-reduced-motion: reduce)";
  const [reduced, setReduced] = useState(() => typeof window !== "undefined" && !!window.matchMedia?.(query).matches);
  useEffect(() => {
    const mq = window.matchMedia?.(query);
    if (!mq) return;
    const on = () => setReduced(mq.matches);
    on();
    mq.addEventListener?.("change", on);
    return () => mq.removeEventListener?.("change", on);
  }, []);
  return reduced;
}

/**
 * The assistant's mark: one orb, configured in one place (composing, light theme, grey ink).
 * Decorative, so hidden from assistive technology; the status text next to it carries the meaning.
 * Paused when asked to, and always under prefers-reduced-motion.
 */
export function AssistantOrb({ size = 20, paused = false, className }: { size?: 64 | 32 | 20; paused?: boolean; className?: string }) {
  const reduced = usePrefersReducedMotion();
  return (
    <span className={`assistant-orb assistant-orb-${size}${className ? ` ${className}` : ""}`} aria-hidden="true" data-paused={paused || reduced}>
      <ThinkingOrb state="composing" size={size} theme="light" paused={paused || reduced} />
    </span>
  );
}
