"use client";

import { useEffect, useRef, useState } from "react";
import type { CSSProperties, ReactNode } from "react";

/**
 * Reveal on view.
 *
 * An IntersectionObserver, not a scroll listener: this fires once per element
 * for the life of the page rather than on every frame of every scroll. It also
 * unobserves on entry, so a long board does not keep several dozen callbacks
 * alive behind it.
 *
 * `once` defaults true because a section that re-animates every time it passes
 * the fold is a section that fights the reader.
 */
export function Reveal({
  children,
  delay = 0,
  as: Tag = "div",
  className = "",
  style,
}: {
  children: ReactNode;
  delay?: number;
  as?: "div" | "section" | "li" | "article";
  className?: string;
  style?: CSSProperties;
}) {
  const ref = useRef<HTMLElement | null>(null);
  const [seen, setSeen] = useState(false);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    // Anything already on screen at load should not wait to be scrolled to.
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setSeen(true);
          io.unobserve(entry.target);
        }
      },
      { rootMargin: "0px 0px -12% 0px", threshold: 0.08 },
    );
    io.observe(node);
    return () => io.disconnect();
  }, []);

  return (
    <Tag
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      ref={ref as any}
      className={`reveal ${seen ? "is-in" : ""} ${className}`.trim()}
      style={{ ["--reveal-delay" as string]: `${delay}ms`, ...style }}
    >
      {children}
    </Tag>
  );
}

/**
 * A number that arrives rather than appears.
 *
 * Odds and percentages roll up from a lower value when they first come into
 * view, which is what a scoreboard does and what a `<span>{value}</span>`
 * never will. The count is driven by requestAnimationFrame against a real
 * clock, so it takes the same time on a 60Hz laptop and a 120Hz phone.
 *
 * Under prefers-reduced-motion it prints the final value immediately: the
 * number is the information, and the movement is not.
 */
export function CountUp({
  to,
  digits = 2,
  prefix = "",
  suffix = "",
  duration = 900,
  className = "",
  style,
}: {
  to: number;
  digits?: number;
  prefix?: string;
  suffix?: string;
  duration?: number;
  className?: string;
  style?: CSSProperties;
}) {
  const ref = useRef<HTMLSpanElement | null>(null);
  const [value, setValue] = useState<number | null>(null);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;

    const reduced =
      typeof matchMedia === "function" &&
      matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced) {
      setValue(to);
      return;
    }

    let raf = 0;
    const io = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return;
        io.unobserve(entry.target);
        const from = to * 0.72;
        const start = performance.now();
        const tick = (now: number) => {
          const t = Math.min(1, (now - start) / duration);
          // Ease out cubic: fast off the mark, settles into the real number.
          const eased = 1 - (1 - t) ** 3;
          setValue(from + (to - from) * eased);
          if (t < 1) raf = requestAnimationFrame(tick);
        };
        raf = requestAnimationFrame(tick);
      },
      { threshold: 0.4 },
    );
    io.observe(node);

    return () => {
      io.disconnect();
      cancelAnimationFrame(raf);
    };
  }, [to, duration]);

  return (
    <span ref={ref} className={className} style={style}>
      {prefix}
      {(value ?? to).toFixed(digits)}
      {suffix}
    </span>
  );
}
