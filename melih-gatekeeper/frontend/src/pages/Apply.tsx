import { AnimatePresence, motion } from "framer-motion";
import { AlertCircle, BarChart3, Building2, HelpCircle, ListChecks, Loader2, Lock, Plus, Send, Sparkles, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { api, ApiError } from "@/api";
import { DecisionBadge } from "@/components/decision";
import { Page, PageHeader } from "@/components/Layout";
import { Button, Card, Input, Select, SectionLabel, Textarea } from "@/components/ui";
import { usePersona, useSamples } from "@/hooks";
import { cn } from "@/lib/utils";
import type { Decision, RawRequest } from "@/types";

const EXPECTED_HINT: Record<string, Decision> = {
  R01: "APPROVE_STATISTICAL", R02: "REJECT", R03: "APPROVE_STATISTICAL", R04: "REJECT", R05: "APPROVE_SPE",
  R06: "REJECT", R07: "APPROVE_STATISTICAL", R08: "APPROVE_STATISTICAL", R09: "APPROVE_STATISTICAL", R10: "REJECT",
};

const GROUP_LABEL: Record<string, string> = {
  requests: "Track examples R01–R10",
  custom: "More examples (jury-style)",
  adversarial: "Edge cases and attacks",
};

const STATS = "health data request";
const RECORDS = "health data access application";

const EMPTY: RawRequest = {
  applicant: { name: "", organisation: "", country: "AT" },
  requested_as: STATS,
  requested_format: "anonymised statistics",
  purpose: "",
  question: "",
  definitions: [""],
};

const DEF_EXAMPLES = [
  "Adult = aged 18 or older on 31 December 2025.",
  "Type 2 diabetes = any condition with an ICD-10 code starting with E11.",
  "Age bands on 31 December 2025: 18-49, 50-64, 65+.",
  "Report per region: adults, adults with type 2 diabetes and the prevalence.",
];

function missingFields(r: RawRequest): string[] {
  const m: string[] = [];
  if (!r.applicant.name.trim()) m.push("your name");
  if (!r.applicant.organisation.trim()) m.push("your organisation");
  if (!r.purpose.trim()) m.push("the purpose");
  if (!r.question.trim()) m.push("your question");
  if (!r.definitions.some((d) => d.trim())) m.push("at least one definition");
  return m;
}

export default function Apply() {
  const { data: samples, isLoading } = useSamples();
  const { persona } = usePersona();
  const nav = useNavigate();
  const [form, setForm] = useState<RawRequest>(EMPTY);
  const [sampleId, setSampleId] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [triedSubmit, setTriedSubmit] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  const missing = missingFields(form);

  const groups = useMemo(() => {
    const m = new Map<string, NonNullable<typeof samples>>();
    (samples ?? []).forEach((s) => {
      const g = s.group ?? (/^R\d/.test(s.id) ? "requests" : "custom");
      m.set(g, [...(m.get(g) ?? []), s]);
    });
    return Array.from(m.entries());
  }, [samples]);

  const patch = (p: Partial<RawRequest>) => {
    setForm((f) => ({ ...f, ...p }));
    setServerError(null);
  };

  const pick = (id: string) => {
    setSampleId(id);
    setServerError(null);
    setTriedSubmit(false);
    const s = samples?.find((x) => x.id === id);
    if (!s) return setForm(EMPTY);
    const j = s.json as RawRequest;
    setForm({
      ...EMPTY,
      ...j,
      applicant: { ...EMPTY.applicant, ...(j.applicant ?? {}) },
      definitions: Array.isArray(j.definitions) && j.definitions.length ? j.definitions : [""],
    });
  };

  const submit = async () => {
    setTriedSubmit(true);
    if (missing.length) return;
    setSubmitting(true);
    setServerError(null);
    try {
      const body: RawRequest = { ...form, definitions: form.definitions.map((d) => d.trim()).filter(Boolean) };
      // keep the sample's id so reruns of a track example stay recognisable; new requests get a server id
      const sample = samples?.find((x) => x.id === sampleId);
      const r = await api.submit(sample ? { ...body, id: (sample.json as RawRequest & { id?: string }).id } : body);
      toast.success(`Request ${r.id} received`, { description: "Checking your request…" });
      nav(`/apply/${encodeURIComponent(r.id)}`);
    } catch (e) {
      setServerError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  };

  const a = form.applicant;
  const defs = form.definitions.length ? form.definitions : [""];
  const show = (field: string) => triedSubmit && missing.includes(field);

  return (
    <Page>
      <PageHeader
        eyebrow="Applicant portal"
        title="Request health data"
        subtitle="Tell us who you are, what you need and why. We check your request against the European Health Data Space rules and answer within seconds."
      />
      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
        <div className="space-y-5">
          {/* example loader */}
          <Card className="flex flex-wrap items-center gap-3 border-dashed bg-sunken/40 p-4">
            <Sparkles size={16} className="text-accent" />
            <span className="text-sm font-medium">Try an example</span>
            <div className="min-w-[260px] flex-1">
              <Select value={sampleId} onChange={(e) => pick(e.target.value)} disabled={isLoading}>
                <option value="">{isLoading ? "Loading examples…" : "Fill the form with an example request…"}</option>
                {groups.map(([g, list]) => (
                  <optgroup key={g} label={GROUP_LABEL[g] ?? g}>
                    {list.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.id} · {s.organisation.split(",")[0]} · {/access/i.test(s.requested_as) ? "records" : "statistics"}
                        {persona === "staff" && EXPECTED_HINT[s.id] ? `  (expected: ${EXPECTED_HINT[s.id]})` : ""}
                      </option>
                    ))}
                  </optgroup>
                ))}
              </Select>
            </div>
            {persona === "staff" && sampleId && EXPECTED_HINT[sampleId] && <DecisionBadge decision={EXPECTED_HINT[sampleId]} size="sm" compact />}
            {sampleId && (
              <Button variant="ghost" size="sm" onClick={() => pick("")}>Clear</Button>
            )}
          </Card>

          {/* 1 who */}
          <Section n={1} icon={<Building2 size={16} />} title="Who is asking?" hint="The person responsible and the organisation that will use the results.">
            <div className="grid gap-3 sm:grid-cols-[1fr_1fr_110px]">
              <Field label="Your name" error={show("your name")}>
                <Input value={a.name} placeholder="Dr. Sophie Lechner" onChange={(e) => patch({ applicant: { ...a, name: e.target.value } })} />
              </Field>
              <Field label="Organisation" error={show("your organisation")}>
                <Input value={a.organisation} placeholder="Medical University of Vienna" onChange={(e) => patch({ applicant: { ...a, organisation: e.target.value } })} />
              </Field>
              <Field label="Country">
                <Input value={a.country} maxLength={2} onChange={(e) => patch({ applicant: { ...a, country: e.target.value.toUpperCase() } })} />
              </Field>
            </div>
          </Section>

          {/* 2 what */}
          <Section n={2} icon={<ListChecks size={16} />} title="What do you need?" hint="Most questions can be answered with statistics. Records are only given when statistics are not enough.">
            <div className="grid gap-3 sm:grid-cols-2">
              <Choice
                active={form.requested_as === STATS}
                onClick={() => patch({ requested_as: STATS, requested_format: "anonymised statistics" })}
                icon={<BarChart3 size={18} />}
                title="Statistics"
                body="Counts, percentages and averages. Groups under 10 people are hidden. You never see individual records."
                tag="Health data request · Art. 69"
              />
              <Choice
                active={form.requested_as === RECORDS}
                onClick={() => patch({ requested_as: RECORDS, requested_format: "pseudonymised records" })}
                icon={<Lock size={18} />}
                title="Records in a secure workspace"
                body="Pseudonymised patient records you can analyse inside a locked environment. Nothing can be downloaded. Explain why statistics are not enough."
                tag="Data access application · Art. 67"
              />
            </div>
          </Section>

          {/* 3 why */}
          <Section n={3} icon={<HelpCircle size={16} />} title="Why do you need it?" hint="Describe what the results will be used for. This decides whether the use is allowed (Art. 53 and 54).">
            <Field label="Purpose" error={show("the purpose")}>
              <Textarea rows={3} value={form.purpose} placeholder="We study regional differences in type 2 diabetes to plan a prevention programme with the regional health authorities."
                onChange={(e) => patch({ purpose: e.target.value })} />
            </Field>
            {form.requested_as === RECORDS && (
              <p className="mt-2 flex items-start gap-1.5 text-sm text-warn">
                <AlertCircle size={14} className="mt-0.5 shrink-0" />
                For records, say why statistics are not enough, for example "training a model needs individual patient histories". Otherwise you receive statistics instead.
              </p>
            )}
          </Section>

          {/* 4 question */}
          <Section n={4} icon={<BarChart3 size={16} />} title="What exactly should we count?" hint="Your question in one sentence, and the definitions we should use. Plain English works; codes make it exact.">
            <Field label="Question" error={show("your question")}>
              <Textarea rows={2} value={form.question} placeholder="How many adults have type 2 diabetes in each region and what is the prevalence?"
                onChange={(e) => patch({ question: e.target.value })} />
            </Field>
            <div className="mt-4">
              <div className="mb-1.5 flex items-baseline justify-between">
                <span className={cn("text-sm font-medium", show("at least one definition") ? "text-reject" : "text-muted")}>Definitions</span>
                <span className="text-xs text-muted">one per line · end with "Report per …: …"</span>
              </div>
              <div className="space-y-2">
                {defs.map((d, i) => (
                  <div key={i} className="flex gap-2">
                    <span className="mt-2.5 w-5 shrink-0 text-right font-mono text-xs text-muted">{i + 1}</span>
                    <Input value={d} placeholder={DEF_EXAMPLES[i % DEF_EXAMPLES.length]}
                      onChange={(e) => patch({ definitions: defs.map((x, j) => (j === i ? e.target.value : x)) })} />
                    <Button variant="ghost" size="icon" disabled={defs.length === 1} onClick={() => patch({ definitions: defs.filter((_, j) => j !== i) })} aria-label="Remove definition">
                      <Trash2 size={14} />
                    </Button>
                  </div>
                ))}
                <Button variant="secondary" size="sm" onClick={() => patch({ definitions: [...defs, ""] })}>
                  <Plus size={14} /> Add definition
                </Button>
              </div>
            </div>
          </Section>

          <Card className="flex flex-wrap items-center justify-between gap-3 p-4">
            <div className="min-w-0 text-sm">
              {triedSubmit && missing.length > 0 ? (
                <span className="inline-flex items-center gap-1.5 text-reject"><AlertCircle size={14} /> Please add {missing.join(", ")}.</span>
              ) : (
                <span className="text-muted">You will see the decision and your results on the next page.</span>
              )}
            </div>
            <Button size="lg" onClick={submit} disabled={submitting}>
              {submitting ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />} Submit request
            </Button>
          </Card>
          <AnimatePresence>
            {serverError && (
              <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                className="rounded-lg border border-reject/30 bg-reject-bg px-3 py-2 text-sm text-reject">
                We could not accept the request: {serverError}
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        <aside className="space-y-4">
          <Card className="sticky top-6 p-5">
            <SectionLabel>What happens next</SectionLabel>
            <ol className="mt-4 space-y-4">
              {[
                ["Purpose check", "Is the use allowed? Marketing, insurance pricing or employment decisions never are (Art. 54)."],
                ["Statistics or records", "Statistics by default. Records only in a secure workspace, and only if needed (Art. 66)."],
                ["Your definitions become a query", "Translated into medical codes by fixed rules. You can read how."],
                ["Privacy checks", "People who opted out are excluded. Groups under 10 people are hidden."],
                ["Decision letter", "In plain language, citing the law, with your results."],
              ].map(([t, b], i) => (
                <li key={t} className="flex gap-3">
                  <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-line bg-sunken font-mono text-xs text-muted">{i + 1}</span>
                  <div>
                    <div className="font-medium">{t}</div>
                    <div className="text-sm text-muted">{b}</div>
                  </div>
                </li>
              ))}
            </ol>
            <div className="mt-5 flex items-center justify-between rounded-lg bg-sunken px-3 py-2 text-sm">
              <span className="text-muted">Typical time</span>
              <span className="font-mono font-medium">&lt; 5 s</span>
            </div>
            <p className="mt-4 text-sm leading-relaxed text-muted">
              Health data never leaves the access body. If AI checks are switched on, only the text of your request is analysed.
            </p>
          </Card>
        </aside>
      </div>
    </Page>
  );
}

function Section({ n, icon, title, hint, children }: { n: number; icon: React.ReactNode; title: string; hint: string; children: React.ReactNode }) {
  return (
    <Card className="p-5">
      <div className="mb-4 flex items-start gap-3">
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-ink font-mono text-xs text-ink-fg">{n}</span>
        <div>
          <div className="flex items-center gap-2 font-semibold tracking-tight">{icon}{title}</div>
          <p className="mt-0.5 text-sm text-muted">{hint}</p>
        </div>
      </div>
      {children}
    </Card>
  );
}

function Choice({ active, onClick, icon, title, body, tag }: { active: boolean; onClick: () => void; icon: React.ReactNode; title: string; body: string; tag: string }) {
  return (
    <button onClick={onClick} type="button"
      className={cn("flex h-full flex-col rounded-xl border p-4 text-left transition-all",
        active ? "border-ink bg-ink/[0.04] shadow-sm ring-1 ring-ink" : "border-line hover:border-ink/40 hover:bg-sunken/60")}>
      <div className="flex items-center gap-2 font-semibold">{icon}{title}</div>
      <p className="mt-1.5 flex-1 text-sm text-muted">{body}</p>
      <span className="mt-3 font-mono text-[11px] uppercase tracking-wide text-muted">{tag}</span>
    </button>
  );
}

function Field({ label, error, children }: { label: string; error?: boolean; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className={cn("mb-1.5 block text-sm font-medium", error ? "text-reject" : "text-muted")}>{label}{error && " · required"}</span>
      {children}
    </label>
  );
}
