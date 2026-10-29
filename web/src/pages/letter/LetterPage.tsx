import { Button, InlineNotification } from "@carbon/react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import type { DecisionLetter } from "../../api/types";
import { PageState, ResultTable } from "../../components/DataComponents";
import { useAppState } from "../../state/AppContext";
import { t } from "../../i18n";

export function LetterPage({ caseId }: { caseId: string }) {
  const { language, setLanguage } = useAppState();
  const [letter, setLetter] = useState<DecisionLetter | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setLetter(await api.letter(caseId, language));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setLoading(false);
    }
  }, [caseId, language]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <section aria-labelledby="page-title">
      <div className="page-toolbar letter-actions">
        <h1 className="page-heading" id="page-title" tabIndex={-1}>{t(language, "letter.print")}</h1>
        <div className="letter-actions__controls">
          <Button kind="ghost" size="sm" onClick={() => setLanguage((current) => current === "de" ? "en" : "de")}>
            {language.toUpperCase()}
          </Button>
          <Button kind="primary" onClick={() => window.print()}>{t(language, "letter.print")}</Button>
        </div>
      </div>
      {loading || error ? (
        <PageState loading={loading} error={error} language={language} onRetry={load} />
      ) : letter ? <LetterDocument letter={letter} language={language} /> : null}
    </section>
  );
}

function LetterDocument({ letter, language }: { letter: DecisionLetter; language: "de" | "en" }) {
  const statAnnex = letter.annex?.type === "statistics" ? letter.annex : null;
  const permitAnnex = letter.annex?.type === "permit" ? letter.annex : null;
  return (
    <article className="letter-page">
      <header className="letter-page__authority">
        <p className="letter-authority">{letter.header.authority}</p>
        <p>{letter.header.authority_address}</p>
        <p className="letter-demo">{letter.header.demo_notice}</p>
      </header>
      {letter.header.draft && (
        <div className="letter-page__notice" role="status">{letter.header.draft_notice}</div>
      )}
      <div className="letter-meta">
        <p><strong>{letter.header.labels.reference}</strong><span className="mono">{letter.header.reference}</span></p>
        <p><strong>{letter.header.labels.date}</strong>{letter.header.date}</p>
      </div>
      <h1 className="letter-document-title">{letter.header.title}</h1>
      <section>
        <h2>{letter.header.labels.applicant}</h2>
        <p>{letter.applicant.name}</p>
        <p>{letter.applicant.organisation}</p>
      </section>
      <section>
        <h2>{letter.header.labels.subject}</h2>
        <p>{letter.subject}</p>
      </section>
      <section>
        <h2>{letter.header.labels.operative}</h2>
        <p>{letter.operative}</p>
      </section>
      <section>
        <h2>{letter.header.labels.reasoning}</h2>
        <ol className="letter-page__paragraphs">
          {letter.reasoning.map((paragraph, index) => <li key={`${index}-${paragraph}`}>{paragraph}</li>)}
        </ol>
      </section>
      {letter.conditions.length > 0 && (
        <section>
          <h2>{letter.header.labels.conditions}</h2>
          <ol className="letter-page__list">
            {letter.conditions.map((condition, index) => <li key={`${index}-${condition}`}>{condition}</li>)}
          </ol>
        </section>
      )}
      {statAnnex && (
        <section>
          <h2>{letter.header.labels.result}</h2>
          <ResultTable
            released={{
              group_dims: statAnnex.group_dims,
              measures: statAnnex.measures,
              rows: statAnnex.rows,
              answer: {},
              gate: { cells: 0, counts_hidden: 0, pct_suppressed: 0, means_suppressed: 0 },
            }}
            language={language}
          />
        </section>
      )}
      {permitAnnex && (
        <section>
          <h2>{letter.header.labels.permit}</h2>
          <dl>
            <div><dt>{language === "de" ? "Genehmigung" : "Permit"}</dt><dd className="mono">{permitAnnex.permit_id}</dd></div>
            <div><dt>{language === "de" ? "Kohorte" : "Cohort"}</dt><dd>{permitAnnex.cohort_size}</dd></div>
            <div><dt>{language === "de" ? "Gültig bis" : "Expires"}</dt><dd>{permitAnnex.expires}</dd></div>
            <div><dt>{language === "de" ? "Datentypen" : "Record types"}</dt><dd>{permitAnnex.tables.join(", ")}</dd></div>
            <div><dt>{language === "de" ? "Nicht bereitgestellt" : "Not provided"}</dt><dd>{permitAnnex.not_tables.join(", ")}</dd></div>
            <div><dt>{language === "de" ? "Berechtigte Personen" : "Authorised people"}</dt><dd>{permitAnnex.persons.join(", ")}</dd></div>
          </dl>
        </section>
      )}
      <section>
        <h2>{letter.header.labels.remedy}</h2>
        <p className="letter-remedy-placeholder">{letter.remedy}</p>
      </section>
      <section>
        <h2>{letter.header.labels.signature}</h2>
        {letter.signature.map((line, index) => <p key={`${index}-${line}`} className={index === letter.signature.length - 1 ? "mono" : undefined}>{line}</p>)}
      </section>
      <section className="letter-articles">
        <h2>{language === "de" ? "Artikel" : "Articles"}</h2>
        <ul>
          {letter.articles.map((article) => <li key={article.n}>Art. {article.n}: {article.title}</li>)}
        </ul>
      </section>
    </article>
  );
}
