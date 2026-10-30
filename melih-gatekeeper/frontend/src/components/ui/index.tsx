// Small hand-written shadcn-style primitives on Radix.
import * as DialogPrimitive from "@radix-ui/react-dialog";
import * as TabsPrimitive from "@radix-ui/react-tabs";
import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import { AlertTriangle, Info, X } from "lucide-react";
import { forwardRef, type ButtonHTMLAttributes, type HTMLAttributes, type ReactNode } from "react";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------- Button
type Variant = "primary" | "secondary" | "ghost" | "danger" | "outline" | "gold";
type Size = "sm" | "md" | "lg" | "icon";
const variants: Record<Variant, string> = {
  primary: "bg-ink text-ink-fg hover:bg-ink/90 shadow-sm",
  secondary: "bg-surface text-ink border border-line hover:bg-sunken",
  outline: "border border-ink/20 text-ink hover:bg-ink/5",
  ghost: "text-ink hover:bg-ink/5",
  danger: "bg-reject text-white hover:bg-reject/90 shadow-sm",
  gold: "bg-gold text-white hover:bg-gold/90 shadow-sm",
};
const sizes: Record<Size, string> = {
  sm: "h-8 px-3 text-sm gap-1.5",
  md: "h-9 px-4 text-base gap-2",
  lg: "h-11 px-5 text-md gap-2",
  icon: "h-8 w-8 justify-center",
};
export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
}
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(({ className, variant = "primary", size = "md", ...props }, ref) => (
  <button
    ref={ref}
    className={cn(
      "inline-flex items-center justify-center rounded-lg font-medium transition-colors disabled:opacity-50 disabled:pointer-events-none whitespace-nowrap select-none",
      variants[variant],
      sizes[size],
      className,
    )}
    {...props}
  />
));
Button.displayName = "Button";

// ---------------------------------------------------------------- Card
export function Card({ className, ...p }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("rounded-xl border border-line bg-surface", className)} {...p} />;
}
export function CardHeader({ title, subtitle, right, className, icon }: { title: ReactNode; subtitle?: ReactNode; right?: ReactNode; className?: string; icon?: ReactNode }) {
  return (
    <div className={cn("flex items-start justify-between gap-4 px-5 pt-4 pb-3", className)}>
      <div className="flex items-start gap-2.5 min-w-0">
        {icon && <div className="mt-0.5 text-muted">{icon}</div>}
        <div className="min-w-0">
          <h3 className="text-md font-semibold tracking-tight">{title}</h3>
          {subtitle && <p className="text-sm text-muted mt-0.5">{subtitle}</p>}
        </div>
      </div>
      {right}
    </div>
  );
}

export function SectionLabel({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("text-xs font-semibold uppercase tracking-[0.08em] text-muted", className)}>{children}</div>;
}

// ---------------------------------------------------------------- Inputs
export const Textarea = forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(({ className, ...p }, ref) => (
  <textarea
    ref={ref}
    className={cn("w-full rounded-lg border border-line bg-surface px-3 py-2 text-base placeholder:text-muted/70 focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent", className)}
    {...p}
  />
));
Textarea.displayName = "Textarea";

export const Input = forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(({ className, ...p }, ref) => (
  <input
    ref={ref}
    className={cn("h-9 w-full rounded-lg border border-line bg-surface px-3 text-base placeholder:text-muted/70 focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent", className)}
    {...p}
  />
));
Input.displayName = "Input";

export function Select({ className, children, ...p }: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <div className="relative">
      <select
        className={cn(
          "h-9 w-full appearance-none rounded-lg border border-line bg-surface pl-3 pr-8 text-base focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent",
          className,
        )}
        {...p}
      >
        {children}
      </select>
      <svg className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-muted" width="12" height="12" viewBox="0 0 12 12">
        <path d="M3 4.5L6 7.5L9 4.5" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" />
      </svg>
    </div>
  );
}

// ---------------------------------------------------------------- Tooltip
export const TooltipProvider = TooltipPrimitive.Provider;
export function Tip({ content, children, side = "top" }: { content: ReactNode; children: ReactNode; side?: "top" | "bottom" | "left" | "right" }) {
  if (!content) return <>{children}</>;
  return (
    <TooltipPrimitive.Root delayDuration={120}>
      <TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger>
      <TooltipPrimitive.Portal>
        <TooltipPrimitive.Content
          side={side}
          sideOffset={6}
          className="z-50 max-w-xs rounded-md bg-ink px-2.5 py-1.5 text-xs leading-snug text-ink-fg shadow-lg data-[state=delayed-open]:animate-in"
        >
          {content}
          <TooltipPrimitive.Arrow className="fill-ink" />
        </TooltipPrimitive.Content>
      </TooltipPrimitive.Portal>
    </TooltipPrimitive.Root>
  );
}

// ---------------------------------------------------------------- Tabs
export const Tabs = TabsPrimitive.Root;
export function TabsList({ className, ...p }: TabsPrimitive.TabsListProps) {
  return <TabsPrimitive.List className={cn("flex items-center gap-1 border-b border-line", className)} {...p} />;
}
export function TabsTrigger({ className, ...p }: TabsPrimitive.TabsTriggerProps) {
  return (
    <TabsPrimitive.Trigger
      className={cn(
        "relative -mb-px inline-flex items-center gap-1.5 px-3 h-10 text-base font-medium text-muted border-b-2 border-transparent transition-colors hover:text-ink data-[state=active]:text-ink data-[state=active]:border-ink",
        className,
      )}
      {...p}
    />
  );
}
export const TabsContent = forwardRef<HTMLDivElement, TabsPrimitive.TabsContentProps>(({ className, ...p }, ref) => (
  <TabsPrimitive.Content ref={ref} className={cn("pt-5 focus:outline-none", className)} {...p} />
));
TabsContent.displayName = "TabsContent";

// ---------------------------------------------------------------- Dialog / Sheet
export const Dialog = DialogPrimitive.Root;
export const DialogTrigger = DialogPrimitive.Trigger;
export const DialogClose = DialogPrimitive.Close;
export function DialogContent({ title, description, children, className }: { title: ReactNode; description?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-ink/30 backdrop-blur-[2px]" />
      <DialogPrimitive.Content
        className={cn(
          "fixed left-1/2 top-1/2 z-50 w-[min(560px,calc(100vw-32px))] -translate-x-1/2 -translate-y-1/2 rounded-xl border border-line bg-surface p-6 shadow-2xl focus:outline-none",
          className,
        )}
      >
        <DialogPrimitive.Title className="text-lg font-semibold tracking-tight">{title}</DialogPrimitive.Title>
        {description ? (
          <DialogPrimitive.Description className="mt-1 text-sm text-muted">{description}</DialogPrimitive.Description>
        ) : (
          <DialogPrimitive.Description className="sr-only">Dialog</DialogPrimitive.Description>
        )}
        <div className="mt-4">{children}</div>
        <DialogPrimitive.Close className="absolute right-4 top-4 rounded-md p-1 text-muted hover:bg-ink/5 hover:text-ink" aria-label="Close">
          <X size={16} />
        </DialogPrimitive.Close>
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  );
}

export function SheetContent({ title, description, children }: { title: ReactNode; description?: ReactNode; children: ReactNode }) {
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-ink/20" />
      <DialogPrimitive.Content className="fixed right-0 top-0 z-50 h-full w-[min(520px,100vw)] overflow-y-auto border-l border-line bg-surface p-7 shadow-2xl focus:outline-none animate-[sheet-in_220ms_cubic-bezier(.2,.7,.2,1)]">
        <DialogPrimitive.Title className="text-lg font-semibold tracking-tight pr-8">{title}</DialogPrimitive.Title>
        {description ? (
          <DialogPrimitive.Description className="mt-1 text-sm text-muted">{description}</DialogPrimitive.Description>
        ) : (
          <DialogPrimitive.Description className="sr-only">Details</DialogPrimitive.Description>
        )}
        <div className="mt-5">{children}</div>
        <DialogPrimitive.Close className="absolute right-5 top-5 rounded-md p-1 text-muted hover:bg-ink/5 hover:text-ink" aria-label="Close">
          <X size={18} />
        </DialogPrimitive.Close>
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  );
}

// ---------------------------------------------------------------- Callout
export function Callout({ tone = "info", title, children, icon, className }: { tone?: "info" | "warn" | "danger" | "ok"; title?: ReactNode; children?: ReactNode; icon?: ReactNode; className?: string }) {
  const tones = {
    info: "bg-spe-bg/70 border-spe/25 text-spe",
    warn: "bg-warn-bg border-warn/30 text-warn",
    danger: "bg-reject-bg border-reject/30 text-reject",
    ok: "bg-stat-bg border-stat/25 text-stat",
  };
  return (
    <div className={cn("flex gap-3 rounded-lg border px-4 py-3", tones[tone], className)}>
      <div className="mt-0.5 shrink-0">{icon ?? (tone === "warn" || tone === "danger" ? <AlertTriangle size={16} /> : <Info size={16} />)}</div>
      <div className="min-w-0 text-sm">
        {title && <div className="font-semibold">{title}</div>}
        {children && <div className={cn("text-ink/80", title && "mt-0.5")}>{children}</div>}
      </div>
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn("rounded-md bg-sunken animate-shimmer", className)}
      style={{ backgroundImage: "linear-gradient(90deg, transparent, rgb(var(--surface) / 0.7), transparent)", backgroundSize: "400px 100%", backgroundRepeat: "no-repeat" }}
    />
  );
}

export function Kbd({ children }: { children: ReactNode }) {
  return <kbd className="rounded border border-line bg-sunken px-1.5 py-0.5 font-mono text-[11px] text-muted">{children}</kbd>;
}

export function Mono({ children, className }: { children: ReactNode; className?: string }) {
  return <span className={cn("font-mono tabular text-[0.92em]", className)}>{children}</span>;
}
