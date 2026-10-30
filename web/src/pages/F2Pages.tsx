import {
  Button,
  InlineNotification,
  Modal,
  RadioButton,
  RadioButtonGroup,
  Select,
  SelectItem,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Tag,
  TextArea,
  TextInput,
  Toggletip,
  ToggletipButton,
  ToggletipContent,
} from "@carbon/react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { CaseSummary, PrecheckResult, RegisterEntry } from "../api/types";
import { DecisionTag, PageState, ResultTable, StatusTag } from "../components/DataComponents";
import { useAppState } from "../state/AppContext";
import { formatDateTime, formatNumber, t } from "../i18n";

type DraftRequest = {
  applicant: { name: string; organisation: string; country: string };
  requested_as: string;
  purpose: string;
  question: string;
  definitions: string[];
};

export function SPEChooserPage() {
  const { language, identity, navigate } = useAppState();
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    void api.applicantCases(identity)
      .then((items) => setCases(items.filter((item) => item.permit_id)))
      .catch((cause) => setError(cause instanceof Error ? cause.message : String(cause)));
  }, [identity]);
  return (
    <section aria-labelledby="page-title">
      <h1 className="page-heading" id="page-title" tabIndex={-1}>{t(language, "title.spe")}</h1>
      {error && <InlineNotification kind="error" lowContrast title={error} />}
      {cases.length === 0
        ? <p className="secondary-text">{language === "de" ? "Für diese Identität liegt keine Datengenehmigung vor." : "This identity has no data permit."}</p>
        : cases.map((item) => (
          <p key={item.id}>
            <Button kind="ghost" onClick={() => navigate(`/apply/spe/${item.permit_id}`)}>
              {item.id} · {item.permit_id}
            </Button>
          </p>
        ))}
    </section>
  );
}

const emptyRequest = (): DraftRequest => ({
  applicant: { name: "", organisation: "", country: "" },
  requested_as: "health data request",
  purpose: "",
  question: "",
  definitions: [""],
});

export function BuilderPage() {
  const { language, identity, identities, ai, navigate } = useAppState();
  const [templates, setTemplates] = useState<Array<{
    id: string; title_de: string; title_en: string; request: Record<string, unknown>;
  }>>([]);
  const [draft, setDraft] = useState<DraftRequest>(emptyRequest);
  const [idea, setIdea] = useState("");
  const [rawMode, setRawMode] = useState(false);
  const [raw, setRaw] = useState("");
  const [precheck, setPrecheck] = useState<PrecheckResult | null>(null);
  const [loadingCheck, setLoadingCheck] = useState(false);
  const [error, setError] = useState("");
  const [suggested, setSuggested] = useState(false);
  const selectedIdentity = identities.find((item) => item.name === identity);

  useEffect(() => {
    void api.templates().then(setTemplates).catch((cause) =>
      setError(cause instanceof Error ? cause.message : String(cause)),
    );
  }, []);

  const request = useMemo(() => ({
    ...draft,
    applicant: selectedIdentity
      ? {
          name: selectedIdentity.name,
          organisation: selectedIdentity.organisation,
          country: selectedIdentity.country,
        }
      : draft.applicant,
  }), [draft, selectedIdentity]);

  useEffect(() => {
    if (!request.purpose.trim() && !request.question.trim()) {
      setPrecheck(null);
      return;
    }
    const timer = window.setTimeout(() => {
      setLoadingCheck(true);
      void api.precheck(request, identity)
        .then(setPrecheck)
        .catch((cause) => setError(cause instanceof Error ? cause.message : String(cause)))
        .finally(() => setLoadingCheck(false));
    }, 400);
    return () => window.clearTimeout(timer);
  }, [identity, request]);

  const applyTemplate = (id: string) => {
    const template = templates.find((item) => item.id === id);
    if (!template) return;
    const value = template.request;
    setDraft((current) => ({
      ...current,
      requested_as: String(value.requested_as ?? current.requested_as),
      purpose: String(value.purpose ?? ""),
      question: String(value.question ?? ""),
      definitions: Array.isArray(value.definitions) ? value.definitions.map(String) : [""],
    }));
    setSuggested(false);
  };

  const setField = (key: "purpose" | "question" | "requested_as", value: string) =>
    setDraft((current) => ({ ...current, [key]: value }));

  const addDefinition = () => setDraft((current) => ({
    ...current,
    definitions: [...current.definitions, ""],
  }));

  const updateDefinition = (index: number, value: string) => setDraft((current) => ({
    ...current,
    definitions: current.definitions.map((item, i) => i === index ? value : item),
  }));

  const removeDefinition = (index: number) => setDraft((current) => ({
    ...current,
    definitions: current.definitions.filter((_, i) => i !== index),
  }));

  const runDraft = async () => {
    setError("");
    try {
      const result = await api.aiDraft({ text: idea, lang: language, purpose: draft.purpose, login: identity });
      setDraft((current) => ({
        ...current,
        requested_as: String(result.draft.requested_as ?? current.requested_as),
        purpose: String(result.draft.purpose ?? current.purpose),
        question: String(result.draft.question ?? current.question),
        definitions: Array.isArray(result.draft.definitions)
          ? result.draft.definitions.map(String)
          : current.definitions,
      }));
      setSuggested(true);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    }
  };

  const parseRaw = () => {
    try {
      const value = JSON.parse(raw) as Partial<DraftRequest>;
      setDraft({ ...emptyRequest(), ...value });
      setError("");
      setRawMode(false);
    } catch {
      setError(language === "de" ? "Ungültiges JSON." : "Invalid JSON.");
    }
  };

  const submit = async () => {
    if (!selectedIdentity) {
      setError(t(language, "applicant.none"));
      return;
    }
    setError("");
    try {
      const submitted = await api.submit(request, identity);
      navigate(`/apply/case/${submitted.id}`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    }
  };

  return (
    <section aria-labelledby="page-title" className="builder-page">
      <h1 className="page-heading" id="page-title" tabIndex={-1}>{t(language, "title.applyNew")}</h1>
      <div className="builder-layout">
        <div className="builder-form">
          <div className="builder-ai">
            <TextArea id="builder-idea"
              labelText={language === "de" ? "Ihre Frage in eigenen Worten" : "Your question in your own words"}
              value={idea} rows={3} maxLength={2000}
              onChange={(event) => setIdea(event.currentTarget.value)} />
            <Button kind="tertiary" disabled={!ai.enabled || idea.trim().length < 5}
              onClick={() => void runDraft()}>
              {language === "de" ? "Entwurf erstellen" : "Create draft"}
            </Button>
            {!ai.enabled && <p className="secondary-text">{language === "de" ? "KI ist nicht aktiv (kein API-Schlüssel)." : "AI is not active (no API key)."}</p>}
            {suggested && (
              <span className="ai-suggestion">
                <Tag type="blue">KI-Vorschlag</Tag>
                <Toggletip>
                  <ToggletipButton label={language === "de" ? "KI-Prüfungen" : "AI checks"} />
                  <ToggletipContent><p>{language === "de"
                    ? "Anschließend wurden derselbe Parser und die Entscheidungsregeln verwendet; Codes wurden gegen die Daten validiert."
                    : "The same parser and decision rules ran afterwards; codes were validated against the data."}</p></ToggletipContent>
                </Toggletip>
              </span>
            )}
          </div>
          <div className="builder-template">
            <p>{language === "de" ? "oder Vorlage wählen" : "or choose a template"}</p>
            <Select id="template-select" labelText={language === "de" ? "Vorlage" : "Template"}
              onChange={(event) => applyTemplate(event.target.value)} value="">
              <SelectItem value="" text={language === "de" ? "Vorlage wählen" : "Choose a template"} />
              {templates.map((item) => (
                <SelectItem key={item.id} value={item.id}
                  text={language === "de" ? item.title_de : item.title_en} />
              ))}
            </Select>
          </div>
          <RadioButtonGroup
            name="request-kind"
            legendText={language === "de" ? "Antragsart" : "Request type"}
            valueSelected={draft.requested_as}
            onChange={(value) => setField("requested_as", String(value))}
          >
            <RadioButton id="kind-request" value="health data request"
              labelText={language === "de" ? "Gesundheitsdatenanfrage · Art. 69" : "Health data request · Art. 69"} />
            <RadioButton id="kind-application" value="health data access application"
              labelText={language === "de" ? "Zugangsantrag · Art. 67" : "Access application · Art. 67"} />
          </RadioButtonGroup>
          <TextArea id="builder-purpose" labelText={t(language, "case.purpose")}
            value={draft.purpose} rows={5} maxLength={4000}
            onChange={(event) => setField("purpose", event.currentTarget.value)} />
          <TextArea id="builder-question" labelText={t(language, "case.question")}
            value={draft.question} rows={4} maxLength={2000}
            onChange={(event) => setField("question", event.currentTarget.value)} />
          <div className="builder-definitions">
            <h2 className="section-heading">{t(language, "case.definitions")}</h2>
            {draft.definitions.map((definition, index) => (
              <div className="builder-definition" key={index}>
                <TextArea id={`builder-definition-${index}`}
                  labelText={language === "de" ? `Definition ${index + 1}` : `Definition ${index + 1}`}
                  value={definition} rows={2} maxLength={1000}
                  onChange={(event) => updateDefinition(index, event.currentTarget.value)} />
                <Button kind="ghost" size="sm" disabled={draft.definitions.length <= 1}
                  onClick={() => removeDefinition(index)}>
                  {language === "de" ? "Entfernen" : "Remove"}
                </Button>
              </div>
            ))}
            <Button kind="ghost" size="sm" onClick={addDefinition}>
              {language === "de" ? "Definition hinzufügen" : "Add definition"}
            </Button>
          </div>
          {error && <InlineNotification kind="error" lowContrast title={error} />}
          <div className="builder-actions">
            <Button kind="primary" onClick={() => void submit()}>
              {language === "de" ? "Antrag einreichen" : "Submit request"}
            </Button>
            <Button kind="ghost" onClick={() => {
              if (!rawMode) setRaw(JSON.stringify(request, null, 2));
              setRawMode((current) => !current);
            }}>
              {rawMode ? (language === "de" ? "JSON schließen" : "Close JSON") : (language === "de" ? "JSON anzeigen/einfügen" : "View/paste JSON")}
            </Button>
          </div>
          {rawMode && (
            <div className="builder-raw">
              <TextArea id="builder-json" labelText="JSON" rows={18} value={raw}
                onChange={(event) => setRaw(event.currentTarget.value)} />
              <Button kind="tertiary" onClick={parseRaw}>{language === "de" ? "Übernehmen" : "Apply JSON"}</Button>
            </div>
          )}
        </div>
        <PrecheckPanel precheck={precheck} loading={loadingCheck} language={language} />
      </div>
    </section>
  );
}

function PrecheckPanel({
  precheck,
  loading,
  language,
}: {
  precheck: PrecheckResult | null;
  loading: boolean;
  language: "de" | "en";
}) {
  return (
    <aside className="precheck-panel" aria-label={language === "de" ? "Vorprüfung" : "Pre-check"}>
      <h2 className="section-heading">{language === "de" ? "Vorprüfung" : "Pre-check"}</h2>
      {loading && <PageState loading language={language} />}
      {!precheck && !loading && <p className="secondary-text">{language === "de" ? "Antragstext eingeben, um die Vorprüfung zu starten." : "Enter request text to start the pre-check."}</p>}
      {precheck && (
        <>
          <DecisionTag decision={precheck.decision.decision} language={language} />
          {precheck.art54.length > 0 && <p className="precheck-decision-code">REJECT [54]</p>}
          <p>{language === "de" ? precheck.decision.reason_de : precheck.decision.reason_en}</p>
          {precheck.art54.map((item) => (
            <InlineNotification key={item.category} kind="error" lowContrast
              title={language === "de" ? item.label_de : item.label_en}
              subtitle={item.evidence.map((evidence) => `„${evidence.phrase}“`).join(" · ")} />
          ))}
          <h3>{language === "de" ? "Begriffe und Codes" : "Terms and codes"}</h3>
          <div className="table-scroll" role="region" aria-label={language === "de" ? "Begriffe und Codes" : "Terms and codes"} tabIndex={0}>
            <table className="data-table">
              <thead><tr><th>{t(language, "case.term")}</th><th>{t(language, "case.code")}</th><th>{t(language, "case.rows")}</th><th>{t(language, "inbox.status")}</th></tr></thead>
              <tbody>{precheck.mappings.flatMap((mapping) => mapping.codes.map((code) => (
                <tr key={`${mapping.name}-${code.code}`}>
                  <td>{mapping.name}</td><td className="mono">{code.code}</td>
                  <td>{code.rows === null ? "—" : String(code.rows)}</td>
                  <td>{mapping.ai ? "KI" : mapping.source.toLowerCase().includes("code list") ? "Code-Liste" : "Definition"}</td>
                </tr>
              )))}</tbody>
            </table>
          </div>
          <dl className="gate-stats">
            <div><dt>{language === "de" ? "Kohortengröße (gerundet)" : "Cohort estimate (rounded)"}</dt><dd>
              {typeof precheck.cohort_estimate === "number" ? formatNumber(precheck.cohort_estimate, language, 0) : precheck.cohort_estimate ?? "—"}
            </dd></div>
            <div><dt>{language === "de" ? "Zellen" : "Cells"}</dt><dd>{precheck.result_shape?.cells ?? "—"}</dd></div>
            <div><dt>{language === "de" ? "Identität" : "Identity"}</dt><dd>{precheck.identity.status}</dd></div>
          </dl>
          {precheck.result_shape && (
            <p className="secondary-text">
              {language === "de" ? "Gruppierungen" : "Groups"}: {precheck.result_shape.group_dims.map((dim) => dim).join(" · ")}
            </p>
          )}
          {precheck.warnings.map((warning) => <p className="secondary-text" key={warning}>{warning}</p>)}
        </>
      )}
    </aside>
  );
}

export function SPEWorkspacePage({ permitId }: { permitId: string }) {
  const { language, identity } = useAppState();
  const [workspace, setWorkspace] = useState<Awaited<ReturnType<typeof api.spe>> | null>(null);
  const [exports, setExports] = useState<Array<Record<string, unknown>>>([]);
  const [sql, setSql] = useState("SELECT * FROM cohort LIMIT 20");
  const [queryResult, setQueryResult] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState("");
  const [title, setTitle] = useState("");
  const [note, setNote] = useState("");
  const [exportOpen, setExportOpen] = useState(false);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setWorkspace(await api.spe(permitId, identity));
      setExports(await api.speExports(permitId, identity));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setLoading(false);
    }
  }, [identity, permitId]);

  useEffect(() => { void load(); }, [load]);

  const runQuery = async () => {
    setError("");
    try {
      setQueryResult(await api.speQuery(permitId, identity, sql));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    }
  };

  const submitExport = async () => {
    try {
      await api.createExport(permitId, { login: identity, sql, title, note });
      setExportOpen(false);
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    }
  };

  const download = async () => {
    try {
      const blob = await api.speCsv(permitId, identity, language);
      saveBlob(blob, `export_${permitId}.csv`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    }
  };

  return (
    <section aria-labelledby="page-title">
      <h1 className="page-heading" id="page-title" tabIndex={-1}>{t(language, "title.spe")}</h1>
      {loading && <PageState loading language={language} />}
      {error && <InlineNotification className="spe-workspace__notification" kind="error" lowContrast title={error} />}
      {workspace && (
        <>
          <dl className="permit-details spe-workspace__meta">
            <div><dt>{language === "de" ? "Genehmigung" : "Permit"}</dt><dd className="mono">{permitId}</dd></div>
            <div><dt>{t(language, "case.expires")}</dt><dd>{formatIsoDate(String(workspace.manifest.expires ?? ""), language)}</dd></div>
            <div><dt>{t(language, "case.persons")}</dt><dd>{String((workspace.manifest.persons_with_access as string[] ?? []).join(", "))}</dd></div>
          </dl>
          <div className="table-scroll spe-workspace__tables" role="region" aria-label={t(language, "case.speTables")} tabIndex={0}>
            <table className="data-table">
              <thead><tr><th>{language === "de" ? "Tabelle" : "Table"}</th><th>{t(language, "case.rows")}</th></tr></thead>
              <tbody>{((workspace.manifest.tables_copied as Array<Record<string, unknown>>) ?? []).map((table, index) => (
                <tr key={String(table.table ?? index)}>
                  <td>{formatTableName(String(table.table ?? ""), language)}</td>
                  <td>{formatNumber(Number(table.rows ?? 0), language, 0)}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
          <h2 className="section-heading spe-workspace__console-heading">{language === "de" ? "SQL-Konsole" : "SQL console"}</h2>
          <TextArea id="spe-sql" labelText="SQL" className="mono" rows={8} value={sql}
            onChange={(event) => setSql(event.currentTarget.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
                event.preventDefault();
                void runQuery();
              }
            }} />
          <div className="spe-workspace__actions">
            <Button kind="primary" onClick={() => void runQuery()}>{language === "de" ? "Abfrage ausführen" : "Run query"}</Button>
            <Button kind="tertiary" onClick={() => setExportOpen(true)}>{language === "de" ? "Export zur Prüfung einreichen" : "Submit export for review"}</Button>
            <Button kind="danger--tertiary" onClick={() => void download()}>{language === "de" ? "Rohdaten herunterladen" : "Download raw data"}</Button>
          </div>
          {queryResult && <QueryResult result={queryResult} language={language} />}
          <h2 className="section-heading">{language === "de" ? "Meine Exporte" : "My exports"}</h2>
          <div className="spe-exports">
            <ExportList rows={exports} language={language} onDownload={(id) => void api.exportCsv(id, identity).then((blob) => saveBlob(blob, `export_${id}.csv`)).catch((cause) => setError(String(cause)))} />
          </div>
          <Modal open={exportOpen} modalHeading={language === "de" ? "Export einreichen" : "Submit export"}
            primaryButtonText={language === "de" ? "Einreichen" : "Submit"}
            secondaryButtonText={t(language, "review.cancel")}
            onRequestClose={() => setExportOpen(false)}
            onRequestSubmit={() => void submitExport()}
            onSecondarySubmit={() => setExportOpen(false)}>
            <div className="review-form">
              <TextInput id="export-title" labelText={language === "de" ? "Titel" : "Title"} value={title} onChange={(event) => setTitle(event.currentTarget.value)} />
              <TextArea id="export-note" labelText={language === "de" ? "Hinweis" : "Note"} value={note} onChange={(event) => setNote(event.currentTarget.value)} />
            </div>
          </Modal>
        </>
      )}
    </section>
  );
}

function QueryResult({ result, language }: { result: Record<string, unknown>; language: "de" | "en" }) {
  const columns = (result.columns as string[]) ?? [];
  const rows = (result.rows as unknown[][]) ?? [];
  return (
    <div className="spe-query-result">
      {Boolean(result.error) && <InlineNotification kind="error" lowContrast title={String(result.error)} />}
      <div className="table-scroll" role="region" aria-label={language === "de" ? "Abfrageergebnis" : "Query result"} tabIndex={0}>
        <table className="data-table">
          <thead><tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr></thead>
          <tbody>{rows.slice(0, 200).map((row, index) => (
            <tr key={index}>{row.map((cell, cellIndex) => <td key={cellIndex}>{String(cell ?? "")}</td>)}</tr>
          ))}</tbody>
        </table>
      </div>
    </div>
  );
}

function ExportList({
  rows, language, onDownload,
}: {
  rows: Array<Record<string, unknown>>;
  language: "de" | "en";
  onDownload: (id: string) => void;
}) {
  if (!rows.length) return <p className="secondary-text">{language === "de" ? "Noch keine Exporte eingereicht." : "No exports submitted yet."}</p>;
  return (
    <div className="table-scroll" role="region" aria-label={language === "de" ? "Exporte" : "Exports"} tabIndex={0}>
      <table className="data-table">
        <thead><tr><th>ID</th><th>{t(language, "inbox.status")}</th><th>{t(language, "case.gate")}</th><th /></tr></thead>
        <tbody>{rows.map((row) => (
          <tr key={String(row.id)}>
            <td className="mono">{String(row.id)}</td>
            <td>{String(row.status)}</td>
            <td>{String((row.check as Record<string, unknown> | undefined)?.result ?? "")}</td>
            <td>{row.status === "approved" && <Button kind="ghost" size="sm" onClick={() => onDownload(String(row.id))}>{language === "de" ? "CSV laden" : "Download CSV"}</Button>}</td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}

function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function formatIsoDate(value: string, language: "de" | "en"): string {
  const date = new Date(`${value.slice(0, 10)}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(language === "de" ? "de-AT" : "en-GB", {
    day: language === "de" ? "2-digit" : "numeric",
    month: language === "de" ? "2-digit" : "long",
    year: "numeric",
    timeZone: "UTC",
  }).format(date);
}

function formatTableName(table: string, language: "de" | "en") {
  const names: Record<string, { de: string; en: string }> = {
    conditions: { de: "Diagnosen", en: "Diagnoses" },
    medications: { de: "Arzneimittel", en: "Medications" },
    observations: { de: "Messwerte", en: "Measurements" },
    cohort: { de: "Kohorte", en: "Cohort" },
  };
  const localized = names[table]?.[language] ?? table;
  return <>{localized} · <span className="mono">{table}</span></>;
}
