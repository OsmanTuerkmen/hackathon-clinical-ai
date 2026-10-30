import { Button, InlineLoading, InlineNotification, Modal, Select, SelectItem, TextArea, TextInput } from "@carbon/react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import type { AuditEntry } from "../../api/types";
import { DecisionTag, PageState, StatusTag } from "../../components/DataComponents";
import { useAppState } from "../../state/AppContext";
import { formatDateTime, formatNumber, t } from "../../i18n";

type ExportRecord = Record<string, unknown> & {
  id: string;
  status: string;
  request_id: string;
  title: string;
  permit_id: string;
  check: { result: string; reasons: Array<{ code: string; de: string; en: string }> };
  columns: string[];
  rows: unknown[][];
};

export function ExportsPage() {
  const { language } = useAppState();
  const [rows, setRows] = useState<ExportRecord[]>([]);
  const [status, setStatus] = useState("");
  const [selected, setSelected] = useState<ExportRecord | null>(null);
  const [reviewOpen, setReviewOpen] = useState(false);
  const [action, setAction] = useState<"approve" | "reject">("approve");
  const [reason, setReason] = useState("");
  const [reviewer, setReviewer] = useState("");
  const [attempted, setAttempted] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setRows(await api.exports(status) as ExportRecord[]);
      setError("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setLoading(false);
    }
  }, [status]);
  useEffect(() => { void load(); }, [load]);

  const saveReview = async () => {
    setAttempted(true);
    if (!selected || reason.trim().length < 20 || reviewer.trim().length < 2) return;
    try {
      await api.reviewExport(selected.id, { action, reason: reason.trim(), reviewer: reviewer.trim() });
      setReviewOpen(false);
      setSelected(null);
      setReason("");
      setReviewer("");
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    }
  };

  return (
    <section aria-labelledby="page-title">
      <h1 className="page-heading" id="page-title" tabIndex={-1}>{t(language, "title.exports")}</h1>
      <div className="page-toolbar">
        <p>{language === "de" ? "Automatische Prüfung und manuelle Freigabe angeforderter Exporte." : "Automatic checks and staff review of requested exports."}</p>
        <Select id="export-status-filter" labelText={t(language, "inbox.status")} value={status}
          onChange={(event) => setStatus(event.target.value)} size="sm">
          <SelectItem value="" text={t(language, "inbox.all")} />
          {["pending_review", "rejected_auto", "approved", "rejected"].map((value) =>
            <SelectItem key={value} value={value} text={value} />)}
        </Select>
      </div>
      {error && <InlineNotification kind="error" lowContrast title={error} />}
      {loading ? <PageState loading language={language} /> : rows.length === 0 ? (
        <PageState empty={t(language, "inbox.empty")} language={language} />
      ) : (
        <div className="table-scroll" role="region" aria-label={t(language, "title.exports")} tabIndex={0}>
          <table className="data-table">
            <thead><tr><th>ID</th><th>{t(language, "inbox.id")}</th><th>{t(language, "case.term")}</th><th>{t(language, "inbox.status")}</th><th>{t(language, "case.gate")}</th><th /></tr></thead>
            <tbody>{rows.map((item) => (
              <tr key={item.id}>
                <td className="mono">{item.id}</td><td className="mono">{item.request_id}</td>
                <td>{item.title}</td><td>{item.status}</td><td>{item.check.result}</td>
                <td><Button kind="ghost" size="sm" onClick={() => setSelected(item)}>{language === "de" ? "Details" : "Details"}</Button></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
      {selected && (
        <section className="export-detail" aria-label={selected.id}>
          <h2 className="section-heading">{selected.title} · {selected.id}</h2>
          <p>{t(language, "case.gate")}: {selected.check.result}</p>
          <ul>{selected.check.reasons.map((item) => <li key={item.code}>{language === "de" ? item.de : item.en}</li>)}</ul>
          <div className="table-scroll" role="region" aria-label={language === "de" ? "Vorschau" : "Preview"} tabIndex={0}>
            <table className="data-table">
              <thead><tr>{selected.columns.map((column) => <th key={column}>{column}</th>)}</tr></thead>
              <tbody>{selected.rows.slice(0, 20).map((row, index) => (
                <tr key={index}>{row.map((value, i) => <td key={i}>{String(value ?? "")}</td>)}</tr>
              ))}</tbody>
            </table>
          </div>
          <Button kind="primary" disabled={selected.status === "rejected_auto"}
            onClick={() => { setAction("approve"); setReviewOpen(true); }}>
            {language === "de" ? "Freigeben" : "Approve"}
          </Button>
          <Button kind="danger--tertiary" onClick={() => { setAction("reject"); setReviewOpen(true); }}>
            {language === "de" ? "Ablehnen" : "Reject"}
          </Button>
        </section>
      )}
      <Modal open={reviewOpen} modalHeading={action === "approve" ? (language === "de" ? "Export freigeben" : "Approve export") : (language === "de" ? "Export ablehnen" : "Reject export")}
        primaryButtonText={language === "de" ? "Prüfung speichern" : "Save review"}
        secondaryButtonText={t(language, "review.cancel")}
        onRequestClose={() => setReviewOpen(false)} onRequestSubmit={() => void saveReview()}
        onSecondarySubmit={() => setReviewOpen(false)}>
        <div className="review-form">
          <TextArea id="export-review-reason" labelText={t(language, "review.reason")} value={reason}
            onChange={(event) => setReason(event.currentTarget.value)} />
          <p className="review-form__counter" aria-live="polite">{reason.length} / 2000</p>
          {attempted && reason.trim().length < 20 && <p role="alert">{t(language, "review.reasonShort")}</p>}
          <TextInput id="export-reviewer" labelText={t(language, "review.reviewer")} value={reviewer}
            onChange={(event) => setReviewer(event.currentTarget.value)} />
          {attempted && reviewer.trim().length < 2 && <p role="alert">{t(language, "review.reviewerRequired")}</p>}
        </div>
      </Modal>
    </section>
  );
}

export function AuditPage() {
  const { language } = useAppState();
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [verify, setVerify] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    try {
      setEntries(await api.auditEntries());
      setError("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { void load(); }, [load]);
  const check = async () => {
    try {
      setVerify(await api.verifyAudit());
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    }
  };
  const ok = Boolean(verify?.ok ?? verify?.valid);
  const count = Number(verify?.entries ?? entries.length);
  return (
    <section aria-labelledby="page-title">
      <h1 className="page-heading" id="page-title" tabIndex={-1}>{t(language, "title.audit")}</h1>
      <Button kind="primary" onClick={() => void check()}>{language === "de" ? "Kette prüfen" : "Verify chain"}</Button>
      {verify && <p role="status">{ok
        ? (language === "de" ? `Kette intakt: ${count} Einträge` : `Chain intact: ${count} entries`)
        : (language === "de" ? `Bruch bei Eintrag ${String(verify.first_bad ?? "N/A")}: ${String(verify.error ?? "")}` : `Break at entry ${String(verify.first_bad ?? "N/A")}: ${String(verify.error ?? "")}`)}</p>}
      {error && <InlineNotification kind="error" lowContrast title={error} />}
      {loading ? <InlineLoading description={t(language, "loading")} /> : (
        <div className="table-scroll" role="region" aria-label={t(language, "title.audit")} tabIndex={0}>
          <table className="data-table"><thead><tr><th>Seq</th><th>{language === "de" ? "Zeit" : "Time"}</th><th>{language === "de" ? "Akteur" : "Actor"}</th><th>{language === "de" ? "Aktion" : "Action"}</th><th>Request</th><th>Hash</th></tr></thead>
            <tbody>{entries.map((entry) => <tr key={entry.seq}><td>{entry.seq}</td><td>{formatDateTime(entry.time, language)}</td><td>{entry.actor}</td><td>{entry.action}</td><td>{entry.request_id}</td><td className="mono">{entry.hash.slice(0, 16)}</td></tr>)}</tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export function EvaluationPage() {
  const { language } = useAppState();
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const run = async () => {
    setLoading(true);
    setError("");
    try {
      setResult(await api.evaluation("all"));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setLoading(false);
    }
  };
  return (
    <section aria-labelledby="page-title">
      <h1 className="page-heading" id="page-title" tabIndex={-1}>{t(language, "title.eval")}</h1>
      <Button kind="primary" onClick={() => void run()} disabled={loading}>
        {language === "de" ? "Auswertung starten" : "Run evaluation"}
      </Button>
      {loading && <InlineLoading description={t(language, "loading")} />}
      {error && <InlineNotification kind="error" lowContrast title={error} />}
      {result && <EvaluationResults result={result} language={language} />}
    </section>
  );
}

function EvaluationResults({
  result,
  language,
}: {
  result: Record<string, unknown>;
  language: "de" | "en";
}) {
  const official = result.official as {
    summary?: Record<string, unknown>;
    rows?: Array<Record<string, unknown>>;
  } | undefined;
  const summary = official?.summary ?? {};
  const metrics = [
    { key: "correct_decisions", label: language === "de" ? "Entscheidungen" : "Decisions", target: "10 / 10" },
    { key: "correct_numbers", label: language === "de" ? "Zahlen" : "Numbers", target: "6 / 6" },
    { key: "privacy_leaks", label: language === "de" ? "Datenschutzverletzungen" : "Privacy leaks", target: "0" },
    { key: "consistency", label: language === "de" ? "Konsistenz" : "Consistency", target: "10 / 10" },
    { key: "slowest_ms", label: language === "de" ? "Langsamste Antwort (ms)" : "Slowest answer (ms)", target: "< 60000" },
  ];
  const ownRows = Array.isArray(result.own)
    ? result.own as Array<Record<string, unknown>>
    : [];
  return (
    <div className="evaluation-results">
      <h2 className="section-heading">{language === "de" ? "Offizielle Suite" : "Official suite"}</h2>
      <div className="table-scroll" role="region" aria-label={language === "de" ? "Metriken" : "Metrics"} tabIndex={0}>
        <table className="data-table">
          <thead><tr><th>{language === "de" ? "Metrik" : "Metric"}</th><th>{language === "de" ? "Ziel" : "Target"}</th><th>{language === "de" ? "Ergebnis" : "Result"}</th></tr></thead>
          <tbody>{metrics.map((metric) => (
            <tr key={metric.key}><th scope="row">{metric.label}</th><td>{metric.target}</td><td>{String(summary[metric.key] ?? "—")}</td></tr>
          ))}</tbody>
        </table>
      </div>
      <h2 className="section-heading">{language === "de" ? "Ergebnisse je Anfrage" : "Per-request results"}</h2>
      <div className="table-scroll" role="region" aria-label={language === "de" ? "Einzelergebnisse" : "Request results"} tabIndex={0}>
        <table className="data-table">
          <thead><tr><th>ID</th><th>{t(language, "inbox.decision")}</th><th>{t(language, "case.tab.result")}</th><th>Leaks</th><th>{t(language, "inbox.status")}</th><th>ms</th></tr></thead>
          <tbody>{(official?.rows ?? []).map((row) => (
            <tr key={String(row.id)}>
              <th scope="row">{String(row.id)}</th>
              <td>{String(row.decision_ok ?? "")}</td>
              <td>{String(row.numbers_ok ?? "")}</td>
              <td>{Array.isArray(row.leaks) ? row.leaks.length : String(row.leaks ?? 0)}</td>
              <td>{String(row.consistent ?? "")}</td>
              <td>{formatNumber(Number(row.max_ms ?? 0), language, 1)}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      <h2 className="section-heading">{language === "de" ? "Strenger Oracle-Abgleich" : "Strict oracle comparison"}</h2>
      <p>{ownRows.length > 0
        ? `${ownRows.filter((row) => row.ok).length} / ${ownRows.length}`
        : (language === "de" ? "Oracle-Datei nicht verfügbar." : "Oracle file unavailable.")}</p>
      {ownRows.length > 0 && (
        <div className="table-scroll" role="region" aria-label={language === "de" ? "Oracle-Anfragen" : "Oracle requests"} tabIndex={0}>
          <table className="data-table">
            <thead><tr><th>ID</th><th>{t(language, "inbox.decision")}</th><th>{language === "de" ? "Erwartet" : "Expected"}</th><th>OK</th><th>{language === "de" ? "Probleme" : "Problems"}</th></tr></thead>
            <tbody>{ownRows.map((row) => (
              <tr key={String(row.id)}>
                <th scope="row">{String(row.id)}</th>
                <td>{String(row.decision)}</td>
                <td>{String(row.expected)}</td>
                <td>{String(row.ok)}</td>
                <td>{((row.problems as string[]) ?? []).join(" · ") || "—"}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </div>
  );
}
