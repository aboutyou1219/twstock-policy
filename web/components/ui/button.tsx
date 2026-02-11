import * as React from "react";

import { cn } from "@/lib/utils";

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "ghost";
}

export function Button({ className, variant = "primary", ...props }: ButtonProps) {
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center rounded-full px-5 py-2 text-sm font-medium transition",
        variant === "primary" &&
          "bg-coral text-white shadow-glow hover:translate-y-[-1px] hover:shadow-lg",
        variant === "ghost" &&
          "border border-white/30 text-white/80 hover:text-white hover:border-white",
        className
      )}
      {...props}
    />
  );
}
