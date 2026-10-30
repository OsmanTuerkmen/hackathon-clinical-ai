import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import type { RegisterEntry } from "../../api/types";
import { DecisionTag, PageState, StatusTag } from "../../components/DataComponents";
import { useAppState } from "../../state/AppContext";
import { formatDate, t } from "../../i18n";

export function RegisterPage() {
  const { language } = useAppState();
  const [entries, setEntries] = useState<RegisterEntry[]>([]);
  const [basis, setBasis] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.register();
      setEntries(response.entries);
      setBasis(response.legal_basis);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <section aria-labelledby="page-title">
      <h1 className="page-heading" id="page-title" tabIndex={-1}>{t(language, "title.register")}</h1>
      <p className="public-register__intro">{t(language, "register.intro")}</p>
      <p className="public-register__basis">
        {t(language, "register.basis")}: {language === "de"
          ? "Art. 57 Abs. 1 lit. j Ziffer ii–iii und Art. 58 Abs. 1 lit. f VO (EU) 2025/327"
          : basis}
      </p>
      {loading || error ? (
        <PageState loading={loading} error={error} language={language} onRetry={load} />
      ) : entries.length === 0 ? (
        <PageState empty={t(language, "register.empty")} language={language} />
      ) : (
        <div className="table-scroll" role="region" aria-label={t(language, "title.register")} tabIndex={0}>
          <table className="data-table register-table">
            <thead>
              <tr>
                <th>{t(language, "register.received")}</th>
                <th>{t(language, "register.reference")}</th>
                <th>{t(language, "register.organisation")}</th>
                <th>{t(language, "register.kind")}</th>
                <th>{t(language, "register.purpose")}</th>
                <th>{t(language, "register.publication")}</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((entry) => (
                <tr key={entry.id}>
                  <td>{formatDate(entry.received, language)}</td>
                  <td className="mono register-reference">{entry.reference}</td>
                  <td>{entry.organisation}</td>
                  <td>{t(language, `kind.${entry.kind}`)}</td>
                  <td>
                    <span>{entry.purpose}</span>
                    {entry.purpose_categories.length > 0 && (
                      <span className="register-categories">
                        {language === "de" ? "Art. 53(1): " : "Art. 53(1): "}
                        {entry.purpose_categories.join(", ")}
                      </span>
                    )}
                    {entry.publication_status === "decided" && (
                      <details className="register-justification">
                        <summary>{t(language, "register.justification")}</summary>
                        <p>{language === "de" ? entry.justification_de : entry.justification_en}</p>
                        {entry.permit && (
                          <div>
                            <strong>{t(language, "register.permit")}</strong>
                            <span> · {formatDate(entry.permit.expires, language)}</span>
                            <ul>
                              {entry.permit.record_types.map((item) => (
                                <li key={item.table}>
                                  {language === "de" ? item.label_de : item.label_en}
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </details>
                    )}
                  </td>
                  <td>
                    {entry.publication_status === "in_review"
                      ? <span>{t(language, "status.in_review")}</span>
                      : entry.decision && <DecisionTag decision={entry.decision} language={language} />}
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
