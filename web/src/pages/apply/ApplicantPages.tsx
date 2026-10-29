import { Button, Tag } from "@carbon/react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import type { CaseSummary } from "../../api/types";
import { DecisionTag, Funnel, PageState, ResultChart, ResultTable, StatusTag } from "../../components/DataComponents";
import { useAppState } from "../../state/AppContext";
import { formatDateTime, t } from "../../i18n";

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
  const { language, identity, navigate } = useAppState();
  const [result, setResult] = useState<ApplicantResult | null>(null);
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

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <section aria-labelledby="page-title">
      <h1 className="page-heading" id="page-title" tabIndex={-1}>
        {result?.summary.id ?? caseId}
      </h1>
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
            <ul className="article-list">
              {result.decision.articles_detail.map((article) => (
                <li key={article.n}>Art. {article.n}: {language === "de" ? article.title_de : article.title_en}</li>
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
                <div className={`result-layout${result.released.group_dims.length === 1 ? "" : " result-layout--table"}`}>
                  <ResultChart released={result.released} language={language} />
                  <ResultTable released={result.released} language={language} />
                  <div className="gate-summary">
                    <h2 className="section-heading">{t(language, "case.gate")}</h2>
                    <p>
                      {result.released.gate.cells} {t(language, "case.cells")} ·{" "}
                      {result.released.gate.counts_hidden
                        + result.released.gate.pct_suppressed
                        + result.released.gate.means_suppressed} {t(language, "case.hidden")}
                    </p>
                  </div>
                </div>
              )}
              {result.funnel && <Funnel steps={result.funnel} language={language} />}
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
