import type { HTMLAttributes } from "react";
import { cn } from "./cn";

/** Loading placeholder. Pass width/height/shape via className. */
export function Skeleton({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      aria-hidden
      className={cn("animate-pulse rounded-2xl border border-white/10 bg-white/[0.04]", className)}
      {...props}
    />
  );
}
