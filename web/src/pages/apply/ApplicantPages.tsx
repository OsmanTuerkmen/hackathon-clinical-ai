import { Button, Tag, Toggletip, ToggletipButton, ToggletipContent } from "@carbon/react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import type { CaseSummary } from "../../api/types";
import {
  DecisionTag,
  differencingReference,
  differencingSubject,
  Funnel,
  PageState,
  ResultChart,
  ResultTable,
  StatusTag,
} from "../../components/DataComponents";
import { useAppState } from "../../state/AppContext";
import { aiProviderModel, formatDateTime, formatNumber, t } from "../../i18n";

type ApplicantResult = Awaited<ReturnType<typeof api.applicantCase>>;

export function ApplicantCasesPage() {
  const { language, identity, navigate } = useAppState();
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!identity) {
      setCases([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      setCases(await api.applicantCases(identity));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setLoading(false);
    }
  }, [identity]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <section aria-labelledby="page-title">
      <h1 className="page-heading" id="page-title" tabIndex={-1}>{t(language, "title.applyCases")}</h1>
      {!identity ? (
        <PageState empty={t(language, "applicant.none")} language={language} />
      ) : loading || error ? (
        <PageState loading={loading} error={error} language={language} onRetry={load} />
      ) : cases.length === 0 ? (
        <PageState empty={t(language, "applicant.noCases")} language={language} />
      ) : (
        <div className="table-scroll" role="region" aria-label={t(language, "title.applyCases")} tabIndex={0}>
          <table className="data-table applicant-cases-table">
            <thead>
              <tr>
                <th>{t(language, "inbox.received")}</th>
                <th>{t(language, "inbox.id")}</th>
                <th>{t(language, "inbox.question")}</th>
                <th>{t(language, "inbox.decision")}</th>
                <th>{t(language, "inbox.status")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {cases.map((item) => (
                <tr key={item.id}>
                  <td>{formatDateTime(item.received_at, language)}</td>
                  <td className="mono">{item.id}</td>
                  <td>{item.question}</td>
                  <td><DecisionTag decision={item.decision} language={language} /></td>
                  <td><StatusTag status={item.status} language={language} /></td>
                  <td className="data-table__number">
                    <Button kind="tertiary" size="sm" onClick={() => navigate(`/apply/case/${item.id}`)}>
                      {language === "de" ? "Öffnen" : "Open"}
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export function ApplicantCasePage({ caseId }: { caseId: string }) {
  const { language, identity, navigate, ai } = useAppState();
  const [result, setResult] = useState<ApplicantResult | null>(null);
  const [explanation, setExplanation] = useState<Awaited<ReturnType<typeof api.aiExplain>> | null>(null);
  const [explaining, setExplaining] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!identity) {
      setError(t(language, "applicant.none"));
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      setResult(await api.applicantCase(caseId, identity));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setLoading(false);
    }
  }, [caseId, identity, language]);

  const explain = async () => {
    setExplaining(true);
    setError("");
    try {
      setExplanation(await api.aiExplain(caseId, identity));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setExplaining(false);
    }
  };

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <section aria-labelledby="page-title">
      <h1 className="page-heading" id="page-title" tabIndex={-1}>
        {language === "de" ? "Antrag" : "Application"} {result?.summary.id ?? caseId}
      </h1>
      {result?.summary.question && (
        <p className="page-subtitle">{result.summary.question}</p>
      )}
      {loading || error ? (
        <PageState loading={loading} error={error} language={language} onRetry={load} />
      ) : result && (
        <>
          <div className={`decision-banner decision-banner--${result.decision.decision.toLowerCase()}`}>
            <DecisionTag decision={result.decision.decision} language={language} />
            <h2>{result.decision.decision === "REJECT"
              ? (language === "de" ? "Der Antrag wurde abgelehnt" : "The request was refused")
              : result.decision.decision === "APPROVE_SPE"
                ? (language === "de" ? "Datengenehmigung erteilt" : "Data permit issued")
                : (language === "de" ? "Statistische Antwort" : "Statistical response")}</h2>
            <p>{language === "de" ? result.decision.reason_de : result.decision.reason_en}</p>
            <ul className="article-list article-list--stacked">
              {result.decision.articles_detail.map((article) => (
                <li key={article.n}>Art. {article.n} · {language === "de" ? article.title_de : article.title_en}</li>
              ))}
            </ul>
          </div>

          {!result.visible ? (
            <div className="held-result" role="status">
              <Tag type="warm-gray">{t(language, "applicant.inReview")}</Tag>
              <p>{result.delivery[language]}</p>
            </div>
          ) : (
            <>
              {result.released && (
                <div className="result-layout result-layout--stack">
                  <div className="result-chart"><ResultChart released={result.released} language={language} /></div>
                  <ResultTable released={result.released} language={language} />
                  <div className="gate-summary">
                    <h2 className="section-heading">{t(language, "case.gate")}</h2>
                    <dl className="gate-stats">
                      <div><dt>{t(language, "case.cells")}</dt><dd>{result.released.gate.cells}</dd></div>
                      <div><dt>{t(language, "case.hiddenCounts")}</dt><dd>{result.released.gate.counts_hidden}</dd></div>
                      <div><dt>{t(language, "case.suppressedValues")}</dt><dd>
                        {result.released.gate.pct_suppressed + result.released.gate.means_suppressed}
                      </dd></div>
                      {(result.released.differencing?.suppressed.length ?? 0) > 0 && (
                        <div>
                          <dt>{language === "de" ? "Differenz-Schutz" : "Differencing protection"}</dt>
                          <dd>{result.released.differencing?.suppressed.length} {language === "de" ? "Zellen" : "cells"}</dd>
                        </div>
                      )}
                    </dl>
                  </div>
                </div>
              )}
              {(result.released?.differencing?.suppressed ?? []).length > 0 && (
                <ul className="differencing-notes">
                  {result.released?.differencing?.suppressed.map((item, index) => (
                    <li key={`${item.measure}-${item.part}-${index}`}>
                      <sup>{index + 1}</sup>{" "}
                      <strong>{differencingSubject(item.against.measure, item.against.group, item.against.part, language)}:</strong>{" "}
                      {language === "de"
                        ? `unterscheidet sich um ${formatNumber(item.difference, language, 0)} Personen von Ihrer früheren Antwort ${item.against.request_id} (${differencingReference(item.against.measure, item.against.group)}). Sonst ließe sich eine Gruppe unter 10 Personen errechnen.`
                        : `differs by ${formatNumber(item.difference, language, 0)} people from your earlier answer ${item.against.request_id} (${differencingReference(item.against.measure, item.against.group)}). Otherwise, a group of fewer than 10 people could be calculated.`}
                    </li>
                  ))}
                </ul>
              )}
              {result.funnel && (
                <section className="applicant-cohort">
                  <h2 className="section-heading">{t(language, "case.cohort")}</h2>
                  <Funnel steps={result.funnel} language={language} />
                  <p className="secondary-text">{t(language, "case.rounded")}</p>
                </section>
              )}
              <div className="applicant-explanation">
                <Button kind="ghost" disabled={!ai.enabled || explaining} onClick={() => void explain()}>
                  {language === "de" ? "Erklärung in einfacher Sprache" : "Explain in plain language"}
                </Button>
                {!ai.enabled && <span className="secondary-text">{language === "de" ? "KI ist nicht aktiv (kein API-Schlüssel)." : "AI is not active (no API key)."}</span>}
                {explanation && (
                  <div>
                    <Tag type="blue">{`${language === "de" ? "KI" : "AI"} · ${aiProviderModel(explanation)}`}</Tag>
                    <Toggletip>
                      <ToggletipButton label={`${language === "de" ? "KI-Hinweis" : "AI note"} · ${aiProviderModel(explanation)}`} />
                      <ToggletipContent><p>{language === "de"
                        ? `Erklärung von ${aiProviderModel(explanation)}. Sie ändert die Entscheidung nicht.`
                        : `Explanation by ${aiProviderModel(explanation)}. It does not change the decision.`}</p></ToggletipContent>
                    </Toggletip>
                    <p>{language === "de" ? explanation.explanation_de : explanation.explanation_en}</p>
                  </div>
                )}
              </div>
              <div className="applicant-result-actions">
                <Button kind="tertiary" onClick={() => navigate(`/letter/${caseId}`)}>
                  {t(language, "applicant.openLetter")}
                </Button>
                {result.spe && (
                  <Button kind="primary" onClick={() => navigate(`/apply/spe/${result.spe?.permit_id}`)}>
                    {t(language, "applicant.openSpe")}
                  </Button>
                )}
              </div>
            </>
          )}
        </>
      )}
    </section>
  );
}

export function F2PlaceholderPage({ route }: { route: string }) {
  const { language } = useAppState();
  const titleKey = route === "/apply/new"
    ? "title.applyNew"
    : route.startsWith("/apply/spe/")
      ? "case.tab.environment"
      : route === "/staff/exports"
        ? "title.exports"
        : route === "/staff/audit"
          ? "title.audit"
          : "title.eval";
  return (
    <section aria-labelledby="page-title">
      <h1 className="page-heading" id="page-title" tabIndex={-1}>{t(language, titleKey)}</h1>
      <p className="f2-placeholder">{t(language, "f2.placeholder")}</p>
    </section>
  );
}
