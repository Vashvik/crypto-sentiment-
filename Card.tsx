import type { HTMLAttributes } from "react";
import { cn } from "./cn";

export type CardVariant = "glass" | "solid" | "inset";
export type CardPadding = "none" | "sm" | "md" | "lg";

const VARIANT: Record<CardVariant, string> = {
  glass: "border border-white/10 bg-white/[0.04] backdrop-blur-md",
  solid: "border border-white/10 bg-slate-950",
  inset: "border border-white/10 bg-black/50",
};

const PADDING: Record<CardPadding, string> = {
  none: "",
  sm: "p-3",
  md: "p-5",
  lg: "p-6",
};

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  variant?: CardVariant;
  padding?: CardPadding;
  /** Adds hover affordance for clickable cards. */
  interactive?: boolean;
}

/** Standard glass surface. Default = translucent card on the dark canvas. */
export function Card({
  variant = "glass",
  padding = "md",
  interactive = false,
  className,
  ...props
}: CardProps) {
  return (
    <div
      className={cn(
        "rounded-2xl",
        VARIANT[variant],
        PADDING[padding],
        interactive && "cursor-pointer transition hover:border-cyan-300/60 hover:bg-white/[0.06]",
        className,
      )}
      {...props}
    />
  );
}
