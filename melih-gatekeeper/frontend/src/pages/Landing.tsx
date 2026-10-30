import { motion } from "framer-motion";
import { ArrowRight, Building2, FileSignature, Gauge, Lock, Scale, ShieldCheck, Sigma } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { Seal } from "@/components/DecisionLetter";
import { Page } from "@/components/Layout";
import { PipelineStepper } from "@/components/PipelineStepper";
import type { Step } from "@/types";

const DEMO_STEPS: Step[] = [
  { key: "received", label: "Received", state: "done", ms: 3 },
  { key: "purpose", label: "Purpose check", state: "done", ms: 1840 },
  { key: "plan", label: "Query plan", state: "done", ms: 3900 },
  { key: "query", label: "Query", state: "done", ms: 120 },
  { key: "privacy", label: "Privacy", state: "done", ms: 4 },
  { key: "decision", label: "Decision", state: "done", ms: 1 },
];

function EntryCard({ to, icon, eyebrow, title, body, cta }: { to: string; icon: ReactNode; eyebrow: string; title: string; body: string; cta: string }) {
  return (
    <Link to={to} className="group block">
      <motion.div
        whileHover={{ y: -3 }}
        transition={{ duration: 0.2 }}
        className="h-full rounded-xl border border-line bg-surface p-7 transition-shadow group-hover:shadow-[0_12px_40px_-12px_rgb(var(--ink)/0.18)]"
      >
        <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-ink text-ink-fg">{icon}</div>
        <div className="mt-5 text-xs font-semibold uppercase tracking-[0.1em] text-gold">{eyebrow}</div>
        <h2 className="mt-1.5 text-lg font-semibold tracking-tight">{title}</h2>
        <p className="mt-2 text-base leading-relaxed text-muted">{body}</p>
        <div className="mt-6 inline-flex items-center gap-1.5 text-base font-medium text-accent">
          {cta} <ArrowRight size={16} className="transition-transform group-hover:translate-x-1" />
        </div>
      </motion.div>
    </Link>
  );
}

export default function Landing() {
  return (
    <Page>
      <section className="relative overflow-hidden rounded-2xl border border-line bg-surface px-10 py-12">
        <div className="pointer-events-none absolute -right-10 -top-10 opacity-[0.08]">
          <Seal size={320} />
        </div>
        <div className="max-w-2xl">
          <div className="text-xs font-semibold uppercase tracking-[0.14em] text-gold">Regulation (EU) 2025/327 · Chapter IV</div>
          <h1 className="mt-3 text-[40px] font-semibold leading-[1.08] tracking-tight">
            An automated Health Data Access Body.
          </h1>
          <p className="mt-4 font-serif text-[20px] italic leading-snug text-ink/80">
            The AI translates. The code computes. The law decides.
          </p>
          <p className="mt-4 max-w-xl text-md leading-relaxed text-muted">
            Every request is checked against the EHDS, translated into a verifiable query plan, computed by deterministic code with the
            small-cell rule, and answered with a plain-language decision letter citing the law. In seconds, not weeks.
          </p>
        </div>
        <div className="mt-10 rounded-xl border border-line bg-bg/60 px-6 pb-4 pt-6">
          <PipelineStepper steps={DEMO_STEPS} outcome="APPROVE_STATISTICAL" />
        </div>
      </section>

      <section className="mt-6 grid gap-5 md:grid-cols-2">
        <EntryCard
          to="/apply"
          icon={<FileSignature size={20} />}
          eyebrow="For researchers, agencies, companies"
          title="Applicant portal"
          body="Submit a health data request or a data access application as JSON. Get a decision letter you can understand, with your statistics or your data permit."
          cta="Submit a request"
        />
        <EntryCard
          to="/staff"
          icon={<Building2 size={20} />}
          eyebrow="For the Health Data Access Body"
          title="HDAB staff console"
          body="Review the queue, read every query plan in plain English, check privacy controls, override decisions and follow the audit trail."
          cta="Open the console"
        />
      </section>

      <section className="mt-6 grid gap-5 md:grid-cols-3">
        {[
          { icon: <Sigma size={18} />, t: "Correct", b: "A closed ICD-10 / ATC / LOINC catalogue and deterministic SQL. Unknown terms go to a human, never a guess." },
          { icon: <Lock size={18} />, t: "Private", b: "Small cells never leave the server, not even for staff. Opt-outs excluded. Secure environment downloads are blocked." },
          { icon: <Scale size={18} />, t: "Accountable", b: "Every decision cites the law, staff can override, and every action lands in the audit trail." },
        ].map((x) => (
          <div key={x.t} className="rounded-xl border border-line bg-surface p-5">
            <div className="flex items-center gap-2 font-semibold">
              <span className="text-gold">{x.icon}</span>
              {x.t}
            </div>
            <p className="mt-2 text-base leading-relaxed text-muted">{x.b}</p>
          </div>
        ))}
      </section>

      <div className="mt-6 flex flex-wrap gap-3 text-sm">
        <Link to="/spe/spe_R05" className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-surface px-3 py-2 font-medium hover:bg-sunken">
          <ShieldCheck size={15} /> Secure processing environment
        </Link>
        <Link to="/metrics" className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-surface px-3 py-2 font-medium hover:bg-sunken">
          <Gauge size={15} /> Metrics scoreboard
        </Link>
      </div>
    </Page>
  );
}
