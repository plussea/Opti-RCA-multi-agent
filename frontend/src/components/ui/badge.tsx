import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "~/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-zinc-300 focus:ring-offset-2",
  {
    variants: {
      variant: {
        default: "border-transparent bg-zinc-800 text-zinc-100",
        secondary: "border-transparent bg-zinc-700 text-zinc-200",
        destructive: "border-transparent bg-red-900 text-red-200",
        outline: "text-zinc-300 border-zinc-700",
        // Status-specific badge variants
        analyzing: "border-transparent bg-blue-900 text-blue-200 animate-pulse",
        diagnosing: "border-transparent bg-blue-900 text-blue-200 animate-pulse",
        planning: "border-transparent bg-blue-900 text-blue-200",
        verifying: "border-transparent bg-blue-900 text-blue-200",
        pending_human: "border-transparent bg-orange-900 text-orange-200",
        approved: "border-transparent bg-green-900 text-green-200",
        rejected: "border-transparent bg-red-900 text-red-200",
        resolved: "border-transparent bg-green-900 text-green-200",
        completed: "border-transparent bg-green-900 text-green-200",
        failed: "border-transparent bg-red-900 text-red-200",
        escalated: "border-transparent bg-red-900 text-red-200",
        perceived: "border-transparent bg-blue-900 text-blue-200",
        needs_review: "border-transparent bg-orange-900 text-orange-200",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
