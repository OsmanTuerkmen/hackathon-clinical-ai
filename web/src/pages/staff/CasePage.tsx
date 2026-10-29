import { Button, InlineNotification } from "@carbon/react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../../api/client";
import type { AuditEntry, CaseDetail, SafeName } from "../../api/types";
import {
  DecisionTag,
  EvidenceText,
  FiveSafeStatus,
  Funnel,
  groupDimensionLabel,
  PageState,
  ResultChart,
  ResultTable,
  StatusTag,
  ValueCell,
} from "../../components/DataComponents";
import { ReviewDialog } from "../../components/ReviewDialog";
import { useAppState } from "../../state/AppContext";
import { formatDateTime, formatNumber, t } from "../../i18n";

type CaseTab = "request" | "decision" | "data" | "result" | "environment" | "people" | "audit";
const TABS: CaseTab[] = ["request", "decision", "data", "result", "environment", "people", "audit"];
const SAFE_NAMES: SafeName[] = ["people", "projects", "data", "settings", "outputs"];

export function CasePage({ caseId }: { caseId: string }) {
  const { language, navigate } = useAppState();
  const [detail, setDetail] = useState<CaseDetail | null>(null);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<CaseTab>("request");
  const [reviewOpen, setReviewOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [caseDetail, auditEntries] = await Promise.all([
        api.case(caseId),
        api.caseAudit(caseId),
      ]);
      setDetail(caseDetail);
      setAudit(auditEntries);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setLoading(false);
    }
  }, [caseId]);

  useEffect(() => {
    void load();
  }, [load]);

  const markedEvidence = useMemo(() => {
    if (!detail) return [];
    const features = detail.result.features;
    return [
      ...features.prohibited.flatMap((item) =>
        item.evidence.map((evidence) => ({ ...evidence, category: "prohibited" as const })),
      ),
      ...features.allowed.flatMap((item) =>
        item.evidence.map((evidence) => ({ ...evidence, category: "allowed" as const })),
      ),
      ...features.justifies_records.map((evidence) => ({
        ...evidence,
        category: "justification" as const,
      })),
      ...features.reidentification.map((evidence) => ({
        ...evidence,
        category: "prohibited" as const,
      })),
    ];
  }, [detail]);

  return (
    <>
      <h1 className="page-heading" id="page-title" tabIndex={-1}>
        {language === "de" ? `Fall ${caseId}` : `Case ${caseId}`}
      </h1>
      {loading && <PageState loading language={language} />}
      {error && <PageState error={error} language={language} onRetry={load} />}
      {!loading && detail && (
        <>
          <CaseHeader detail={detail} language={language} onReview={() => setReviewOpen(true)} />
          <FiveSafesOverview detail={detail} language={language} onSelectTab={setTab} />
          <div
            className="case-tabs"
            role="tablist"
            aria-label={language === "de" ? "Fallbereiche" : "Case sections"}
            onKeyDown={(event) => {
              const current = TABS.indexOf(tab);
              if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
                event.preventDefault();
                const delta = event.key === "ArrowRight" ? 1 : -1;
                const next = TABS[(current + delta + TABS.length) % TABS.length];
                setTab(next);
                document.getElementById(`case-tab-${next}`)?.focus();
              }
            }}
          >
            {TABS.map((item) => (
              <button
                className={`case-tab${tab === item ? " case-tab--selected" : ""}`}
                id={`case-tab-${item}`}
                key={item}
                type="button"
                role="tab"
                aria-selected={tab === item}
                tabIndex={tab === item ? 0 : -1}
                aria-controls={`case-panel-${item}`}
                onClick={() => setTab(item)}
              >
                {t(language, `case.tab.${item === "environment" ? "environment" : item}`)}
              </button>
            ))}
          </div>
          <section
            className="case-panel"
            id={`case-panel-${tab}`}
            role="tabpanel"
            aria-labelledby={`case-tab-${tab}`}
            tabIndex={0}
          >
            {tab === "request" && (
              <RequestPanel detail={detail} language={language} evidence={markedEvidence} />
            )}
            {tab === "decision" && <DecisionPanel detail={detail} language={language} />}
            {tab === "data" && <DataPanel detail={detail} language={language} />}
            {tab === "result" && <ResultPanel detail={detail} language={language} />}
            {tab === "environment" && (
              <EnvironmentPanel
                detail={detail}
                language={language}
                onOpenSpe={() => detail.result.spe && navigate(`/apply/spe/${detail.result.spe.permit_id}`)}
              />
            )}
            {tab === "people" && <PeoplePanel detail={detail} language={language} />}
            {tab === "audit" && <AuditPanel entries={audit} language={language} />}
          </section>
          <ReviewDialog
            open={reviewOpen}
            caseId={caseId}
            language={language}
            onClose={() => setReviewOpen(false)}
            onSaved={() => void load()}
          />
        </>
      )}
    </>
  );
}

function CaseHeader({
  detail,
  language,
  onReview,
}: {
  detail: CaseDetail;
  language: "de" | "en";
  onReview: () => void;
}) {
  const { summary } = detail;
  return (
    <header className="case-header">
      <div className="case-header__identity">
        <p className="case-header__applicant">
          <strong>{summary.applicant.name}</strong>
          <span>{summary.applicant.organisation}</span>
        </p>
        <div className="case-header__metadata">
          <span>{formatDateTime(summary.received_at, language)}</span>
          <span className="mono">{summary.id}</span>
          <DecisionTag decision={summary.decision} language={language} />
          <StatusTag status={summary.status} language={language} />
          <span className="case-header__articles">
            {detail.result.decision.articles_detail.map((article) => (
              <span key={article.n}>
                Art. {article.n}: {language === "de" ? article.title_de : article.title_en}
              </span>
            ))}
          </span>
        </div>
      </div>
      <Button kind="primary" onClick={onReview}>
        {t(language, "case.review")}
      </Button>
    </header>
  );
}

function FiveSafesOverview({
  detail,
  language,
  onSelectTab,
}: {
  detail: CaseDetail;
  language: "de" | "en";
  onSelectTab: (tab: CaseTab) => void;
}) {
  const questions: Record<SafeName, string> = {
    people: language === "de" ? "Wer fragt?" : "Who is asking?",
    projects: language === "de" ? "Wozu?" : "For what purpose?",
    data: language === "de" ? "Welche Daten?" : "Which data?",
    settings: language === "de" ? "Wo wird gerechnet?" : "Where is it processed?",
    outputs: language === "de" ? "Was verlässt die Stelle?" : "What leaves the access body?",
  };
  return (
    <section className="case-section" aria-labelledby="five-safes-heading">
      <h2 className="section-heading" id="five-safes-heading">
        {language === "de" ? "Five Safes" : "Five Safes"}
      </h2>
      <div className="table-scroll" role="region" aria-label={t(language, "inbox.safes")} tabIndex={0}>
        <table className="data-table five-safes-table">
          <thead>
            <tr>
              <th scope="col">{language === "de" ? "Safe" : "Safe"}</th>
              <th scope="col">{language === "de" ? "Frage" : "Question"}</th>
              <th scope="col">{language === "de" ? "Status" : "Status"}</th>
              <th scope="col">{language === "de" ? "Feststellung" : "Finding"}</th>
              <th scope="col">{language === "de" ? "Nachweis" : "Evidence"}</th>
            </tr>
          </thead>
          <tbody>
            {SAFE_NAMES.map((name) => {
              const safe = detail.result.five_safes[name];
              const summary = language === "de" ? safe.summary_de : safe.summary_en;
              return (
                <tr key={name}>
                  <th scope="row">{t(language, `safe.name.${name}`)}</th>
                  <td>{questions[name]}</td>
                  <td><FiveSafeStatus status={safe.status} language={language} /></td>
                  <td>{summary}</td>
                  <td>
                    <Button
                      kind="ghost"
                      size="sm"
                      onClick={() => onSelectTab(({
                        people: "people",
                        projects: "decision",
                        data: "data",
                        settings: "environment",
                        outputs: "result",
                      } as Record<SafeName, CaseTab>)[name])}
                    >
                      {language === "de" ? "Zum Nachweis" : "Show evidence"}
                    </Button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function RequestPanel({
  detail,
  language,
  evidence,
}: {
  detail: CaseDetail;
  language: "de" | "en";
  evidence: Array<{
    phrase: string;
    field: string;
    start: number;
    end: number;
    category: "prohibited" | "allowed" | "justification";
  }>;
}) {
  const request = detail.result.request;
  const purpose = String(request.purpose ?? "");
  const question = String(request.question ?? "");
  const organisation = String(request.applicant?.organisation ?? "");
  return (
    <div className="case-section">
      <h2 className="section-heading">{t(language, "case.purpose")}</h2>
      <p>
        <EvidenceText text={purpose} field="purpose" evidence={evidence} />
      </p>
      <h2 className="section-heading">{t(language, "case.question")}</h2>
      <p>
        <EvidenceText text={question} field="question" evidence={evidence} />
      </p>
      <h2 className="section-heading">{t(language, "inbox.applicant")}</h2>
      <p>
        {request.applicant?.name ? `${request.applicant.name} · ` : ""}
        <EvidenceText text={organisation} field="organisation" evidence={evidence} />
      </p>
      <EvidenceLabels detail={detail} language={language} />
      <h2 className="section-heading">{t(language, "case.definitions")}</h2>
      <ol className="definition-list">
        {(request.definitions ?? []).map((definition, index) => (
          <li key={`${index}-${definition}`}>{definition}</li>
        ))}
      </ol>
    </div>
  );
}

function EvidenceLabels({ detail, language }: { detail: CaseDetail; language: "de" | "en" }) {
  const labels = [
    ...detail.result.features.prohibited.map((item) => ({
      id: `prohibited-${item.category}`,
      category: "prohibited",
      text: `${language === "de" ? item.label_de : item.label_en} · Art. 54`,
      phrases: item.evidence.map((evidence) => evidence.phrase),
    })),
    ...detail.result.features.allowed.map((item) => ({
      id: `allowed-${item.category}`,
      category: "allowed",
      text: `${language === "de" ? item.de : item.en} · Art. 53`,
      phrases: item.evidence.map((evidence) => evidence.phrase),
    })),
    ...(detail.result.features.justifies_records.length > 0 ? [{
      id: "justification",
      category: "justification",
      text: language === "de" ? "Begründung für Einzeldaten · Art. 66" : "Justification for individual data · Art. 66",
      phrases: detail.result.features.justifies_records.map((evidence) => evidence.phrase),
    }] : []),
  ];
  if (labels.length === 0) return null;
  return (
    <ul className="evidence-category-list" aria-label={language === "de" ? "Belegkategorien" : "Evidence categories"}>
      {labels.map((item) => (
        <li key={item.id} className={`evidence-category evidence-category--${item.category}`}>
          <span className="evidence-category__marker" aria-hidden="true" />
          <strong>{item.text}</strong>
          <span>{item.phrases.join(" · ")}</span>
        </li>
      ))}
    </ul>
  );
}

function DecisionPanel({ detail, language }: { detail: CaseDetail; language: "de" | "en" }) {
  const { result } = detail;
  return (
    <div className="case-section">
      <h2 className="section-heading">{t(language, "case.trace")}</h2>
      <ol className="trace-list">
        {result.decision.trace.map((step) => (
          <li key={`${step.step}-${step.rule}`}>
            <span className="trace-step">{step.step}</span>
            <span>
              <strong>{step.rule}</strong>
              {step.evidence.length > 0 && (
                <span className="trace-evidence">{step.evidence.join(" · ")}</span>
              )}
            </span>
            <span>{step.result ? (language === "de" ? "Ja" : "Yes") : (language === "de" ? "Nein" : "No")}</span>
          </li>
        ))}
      </ol>
      <h2 className="section-heading">{t(language, "case.articles")}</h2>
      <ul>
        {result.decision.articles_detail.map((article) => (
          <li key={article.n}>Art. {article.n}: {language === "de" ? article.title_de : article.title_en}</li>
        ))}
      </ul>
      {result.ai.opinion && (
        <section className="case-section">
          <h2 className="section-heading">{t(language, "case.aiOpinion")}</h2>
          <pre className="sql-block">{JSON.stringify(result.ai.opinion, null, 2)}</pre>
        </section>
      )}
    </div>
  );
}

function DataPanel({ detail, language }: { detail: CaseDetail; language: "de" | "en" }) {
  const { result } = detail;
  return (
    <div className="case-section">
      <h2 className="section-heading">{t(language, "case.mappings")}</h2>
      <div className="table-scroll" role="region" aria-label={t(language, "case.mappings")} tabIndex={0}>
        <table className="data-table">
          <thead>
            <tr>
              <th>{t(language, "case.term")}</th>
              <th>{t(language, "case.system")}</th>
              <th>{t(language, "case.code")}</th>
              <th>{t(language, "case.label")}</th>
              <th className="data-table__number">{t(language, "case.rows")}</th>
            </tr>
          </thead>
          <tbody>
            {result.mappings.flatMap((mapping) =>
              mapping.codes.map((code) => (
                <tr key={`${mapping.name}-${code.system}-${code.code}`}>
                  <td>{mapping.name}</td>
                  <td>{code.system}</td>
                  <td className="mono">{code.code}</td>
                  <td>{code.label ?? "—"}</td>
                  <td className="data-table__number">
                    {code.rows === null ? "—" : <ValueCell value={code.rows} language={language} type="count" />}
                  </td>
                </tr>
              )),
            )}
          </tbody>
        </table>
      </div>
      <h2 className="section-heading">{t(language, "case.plan")}</h2>
      <p>
        {result.plan.unit}
        {result.plan.groups.map((group) => {
          const labels = group.bands?.map((band) => band.label)
            ?? group.years?.map(String)
            ?? [];
          const groupText = groupDimensionLabel(group.dim, language);
          return ` · ${groupText}${labels.length ? ` (${labels.join(", ")})` : ""}`;
        }).join("")}
      </p>
      <ul>
        {result.plan.measures.map((measure) => (
          <li key={measure.key}>{measure.label} ({measure.type})</li>
        ))}
      </ul>
      {result.plan.warnings.length > 0 && (
        <InlineNotification
          kind="warning"
          lowContrast
          title={language === "de" ? "Parserhinweise" : "Parser warnings"}
          subtitle={result.plan.warnings.join(" · ")}
        />
      )}
      <h2 className="section-heading">{t(language, "case.sql")}</h2>
      {result.sql ? <pre className="sql-block"><code>{result.sql}</code></pre> : <p>—</p>}
      <h2 className="section-heading">{t(language, "case.funnel")}</h2>
      <Funnel steps={result.funnel} language={language} />
      <p className="secondary-text">
        {formatNumber(result.opted_out_excluded, language, 0)} {t(language, "case.optouts")}
      </p>
    </div>
  );
}

function ResultPanel({ detail, language }: { detail: CaseDetail; language: "de" | "en" }) {
  const released = detail.result.released;
  return (
    <div className="case-section">
      <h2 className="section-heading">{t(language, "case.tab.result")}</h2>
      {!released ? (
        <p>{t(language, "case.noResults")}</p>
      ) : (
        <div className={`result-layout${released.group_dims.length === 1 ? "" : " result-layout--table"}`}>
          <ResultChart released={released} language={language} />
          <ResultTable released={released} language={language} />
          <section>
            <h3>{t(language, "case.gate")}</h3>
            <dl className="gate-stats">
              <div><dt>{t(language, "case.cells")}</dt><dd>{released.gate.cells}</dd></div>
              <div><dt>{t(language, "case.hidden")}</dt><dd>
                {released.gate.counts_hidden + released.gate.pct_suppressed + released.gate.means_suppressed}
              </dd></div>
            </dl>
          </section>
        </div>
      )}
    </div>
  );
}

function EnvironmentPanel({
  detail,
  language,
  onOpenSpe,
}: {
  detail: CaseDetail;
  language: "de" | "en";
  onOpenSpe: () => void;
}) {
  const manifest = detail.result.spe;
  if (!manifest) {
    return <p>{t(language, "case.processedInside")}</p>;
  }
  return (
    <div className="case-section">
      <h2 className="section-heading">{manifest.permit_id}</h2>
      <dl className="permit-details">
        <div><dt>{t(language, "case.expires")}</dt><dd>{manifest.expires}</dd></div>
        <div><dt>{t(language, "case.persons")}</dt><dd>{manifest.persons_with_access.join(", ")}</dd></div>
      </dl>
      <h3>{t(language, "case.speTables")}</h3>
      <table className="data-table">
        <thead><tr><th>{t(language, "case.term")}</th><th>{t(language, "case.rows")}</th></tr></thead>
        <tbody>
          {manifest.tables_copied.map((record) => (
            <tr key={record.table}>
              <td>{tableName(record.table, language, record.note)}</td>
              <td className="data-table__number">{formatNumber(record.rows, language, 0)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <h3>{t(language, "case.notCopied")}</h3>
      <ul>{manifest.tables_not_copied.map((table) => <li key={table}>{tableName(table, language)}</li>)}</ul>
      <Button kind="tertiary" onClick={onOpenSpe}>
        {language === "de" ? "SPE-Arbeitsbereich öffnen" : "Open SPE workspace"}
      </Button>
      <pre className="sql-block">{manifest.cohort_sql}</pre>
    </div>
  );
}

function PeoplePanel({ detail, language }: { detail: CaseDetail; language: "de" | "en" }) {
  return (
    <div className="case-section">
      <h2 className="section-heading">{t(language, "safe.people")}</h2>
      <table className="data-table">
        <thead>
          <tr>
            <th>{language === "de" ? "Prüfung" : "Check"}</th>
            <th>{language === "de" ? "Aussteller" : "Issuer"}</th>
            <th>{t(language, "inbox.status")}</th>
            <th>{language === "de" ? "Ergebnis" : "Finding"}</th>
          </tr>
        </thead>
        <tbody>
          {detail.result.who.checks.map((check) => (
            <tr key={check.id}>
              <th scope="row">{check.id}</th>
              <td>{check.issuer ?? "—"}</td>
              <td>{check.ok ? t(language, "safe.pass") : t(language, "safe.fail")}</td>
              <td>{language === "de" ? check.detail_de : check.detail_en}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <h3>{language === "de" ? "Plausibilität" : "Plausibility"}</h3>
      {detail.result.who.flags.length === 0
        ? <p>{t(language, "safe.pass")}</p>
        : (
          <ul>
            {detail.result.who.flags.map((flag) => (
              <li key={flag.id}>{language === "de" ? flag.de : flag.en}</li>
            ))}
          </ul>
        )}
    </div>
  );
}

function AuditPanel({ entries, language }: { entries: AuditEntry[]; language: "de" | "en" }) {
  if (entries.length === 0) return <p>{t(language, "inbox.empty")}</p>;
  return (
    <div className="table-scroll" role="region" aria-label={language === "de" ? "Prüfprotokoll" : "Audit log"} tabIndex={0}>
      <table className="data-table">
        <thead>
          <tr>
            <th>Seq</th>
            <th>{language === "de" ? "Zeit" : "Time"}</th>
            <th>{language === "de" ? "Akteur" : "Actor"}</th>
            <th>{language === "de" ? "Aktion" : "Action"}</th>
            <th>{language === "de" ? "Details" : "Details"}</th>
            <th>Hash</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((entry) => (
            <tr key={entry.seq}>
              <td>{entry.seq}</td>
              <td>{formatDateTime(entry.time, language)}</td>
              <td>{entry.actor}</td>
              <td>{entry.action}</td>
              <td>{JSON.stringify(entry.details)}</td>
              <td className="mono">{entry.hash.slice(0, 12)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function tableName(table: string, language: "de" | "en", note?: string | null): string {
  const names: Record<string, [string, string]> = {
    conditions: ["Diagnosen", "conditions"],
    medications: ["Medikation", "medications"],
    observations: ["Messwerte", "measurements"],
    encounters: ["Kontakte", "encounters"],
    patients: ["Stammdaten", "demographics"],
  };
  const name = names[table]?.[language === "de" ? 0 : 1] ?? table;
  const match = note?.match(/\d{1,6}-\d/g);
  if (table === "observations" && match?.length) {
    return language === "de"
      ? `${name} (nur LOINC ${match.join(", ")})`
      : `${name} (LOINC ${match.join(", ")} only)`;
  }
  return name;
}
