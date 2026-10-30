import { Database, FlaskConical, Moon, Sun, Wifi } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { setModePreference } from "@/api";
import { useApiMode, usePersona, type Persona } from "@/hooks";
import { cn } from "@/lib/utils";
import { Tip } from "./ui";

export function Logo({ size = 30 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden>
      <rect width="32" height="32" rx="8" fill="rgb(var(--ink))" />
      <path d="M16 6l8 3v6c0 5-3.4 8.7-8 10-4.6-1.3-8-5-8-10V9l8-3z" fill="none" stroke="rgb(var(--gold))" strokeWidth="1.8" />
      <path d="M12.5 15.5l2.5 2.5 4.5-5" fill="none" stroke="rgb(var(--ink-fg))" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function NavItem({ to, children, end }: { to: string; children: ReactNode; end?: boolean }) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        cn(
          "relative inline-flex h-9 items-center rounded-lg px-3 text-base font-medium transition-colors",
          isActive ? "bg-ink/[0.06] text-ink" : "text-muted hover:text-ink hover:bg-ink/[0.03]",
        )
      }
    >
      {children}
    </NavLink>
  );
}

function PersonaToggle() {
  const { persona, setPersona } = usePersona();
  const loc = useLocation();
  const nav = useNavigate();
  const go = (p: Persona) => {
    setPersona(p);
    const m = loc.pathname.match(/^\/(?:apply|staff\/requests)\/([^/]+)/);
    if (p === "applicant") nav(m ? `/apply/${m[1]}` : "/apply");
    else nav(m ? `/staff/requests/${m[1]}` : "/staff");
  };
  return (
    <div className="flex items-center gap-2">
      <span className="hidden text-sm text-muted xl:inline">Viewing as</span>
      <div className="flex rounded-lg border border-line bg-sunken p-0.5">
        {(["applicant", "staff"] as Persona[]).map((p) => (
          <button
            key={p}
            onClick={() => go(p)}
            className={cn(
              "h-7 rounded-md px-3 text-sm font-medium transition-all",
              persona === p ? "bg-surface text-ink shadow-sm" : "text-muted hover:text-ink",
            )}
          >
            {p === "applicant" ? "Applicant" : "HDAB Staff"}
          </button>
        ))}
      </div>
    </div>
  );
}

function ModePill() {
  const mode = useApiMode();
  if (!mode) return null;
  const mock = mode === "mock";
  return (
    <Tip content={mock ? "Backend unreachable or mock forced: realistic in-browser data built from the track samples. Click to retry the live backend." : "Connected to the FastAPI backend. Click to force mock mode."}>
      <button
        onClick={() => setModePreference(mock ? "live" : "mock")}
        className={cn(
          "inline-flex h-7 items-center gap-1.5 rounded-full border px-2.5 text-xs font-medium",
          mock ? "border-warn/30 bg-warn-bg text-warn" : "border-stat/25 bg-stat-bg text-stat",
        )}
      >
        {mock ? <FlaskConical size={12} /> : <Wifi size={12} />}
        {mock ? "Mock data" : "Live API"}
      </button>
    </Tip>
  );
}

function ThemeToggle() {
  const [dark, setDark] = useState(() => {
    try {
      return localStorage.getItem("ehds.theme") === "dark";
    } catch {
      return false;
    }
  });
  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    try {
      localStorage.setItem("ehds.theme", dark ? "dark" : "light");
    } catch {
      /* ignore */
    }
  }, [dark]);
  return (
    <button onClick={() => setDark(!dark)} className="flex h-8 w-8 items-center justify-center rounded-lg text-muted hover:bg-ink/5 hover:text-ink" aria-label="Toggle dark mode">
      {dark ? <Sun size={16} /> : <Moon size={16} />}
    </button>
  );
}

export function Layout() {
  const { persona } = usePersona();
  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-30 border-b border-line bg-bg/85 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-[1320px] items-center gap-6 px-6">
          <NavLink to="/" className="flex shrink-0 items-center gap-3">
            <Logo />
            <div className="leading-tight">
              <div className="text-[15px] font-semibold tracking-tight">EHDS Gatekeeper</div>
              <div className="hidden text-xs text-muted md:block">Health Data Access Body · Austria (demo)</div>
            </div>
          </NavLink>
          <nav className="flex items-center gap-0.5">
            <NavItem to="/apply">Applicant</NavItem>
            <NavItem to="/staff">Staff console</NavItem>
            <NavItem to="/spe/spe_R05">SPE</NavItem>
            <NavItem to="/metrics">Metrics</NavItem>
          </nav>
          <div className="ml-auto flex items-center gap-3">
            <ModePill />
            <PersonaToggle />
            <ThemeToggle />
          </div>
        </div>
      </header>
      <main className="flex-1" data-persona={persona}>
        <Outlet />
      </main>
      <footer className="sticky bottom-0 z-20 border-t border-line bg-surface/90 backdrop-blur">
        <div className="mx-auto flex h-10 max-w-[1320px] items-center gap-x-5 overflow-hidden whitespace-nowrap px-6 text-xs text-muted">
          <span className="inline-flex items-center gap-1.5">
            <Database size={12} /> Synthetic data only
          </span>
          <span className="h-3 w-px bg-line" />
          <span><span className="font-mono text-ink">20,000</span> patients</span>
          <span className="h-3 w-px bg-line" />
          <span><span className="font-mono text-ink">839</span> opted out, excluded everywhere (Art. 71)</span>
          <span className="hidden h-3 w-px bg-line md:block" />
          <span className="hidden md:inline">Patient data never sent to AI</span>
          <span className="ml-auto hidden font-medium text-ink/70 lg:inline">Reg. (EU) 2025/327 · Chapter IV</span>
        </div>
      </footer>
    </div>
  );
}

export function Page({ children, className, wide }: { children: ReactNode; className?: string; wide?: boolean }) {
  return <div className={cn("mx-auto px-6 py-8", wide ? "max-w-[1320px]" : "max-w-[1180px]", className)}>{children}</div>;
}

export function PageHeader({ title, subtitle, right, eyebrow }: { title: ReactNode; subtitle?: ReactNode; right?: ReactNode; eyebrow?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        {eyebrow && <div className="mb-1.5 text-xs font-semibold uppercase tracking-[0.1em] text-gold">{eyebrow}</div>}
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {subtitle && <p className="mt-1 max-w-2xl text-md text-muted">{subtitle}</p>}
      </div>
      {right}
    </div>
  );
}
