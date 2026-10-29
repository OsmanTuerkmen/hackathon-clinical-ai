import {
  Button,
  DataTable,
  Search as CarbonSearch,
  Tag,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableHeader,
  TableRow,
} from "@carbon/react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../../api/client";
import type { CaseSummary } from "../../api/types";
import { DecisionTag, PageState, SafeIndicators, StatusTag } from "../../components/DataComponents";
import { useAppState } from "../../state/AppContext";
import { formatDateTime, t } from "../../i18n";
import { KeyboardHelp } from "../../components/DataComponents";

type StatusFilter = "all" | "review_needed" | "held_identity" | "automatic" | "released";

const FILTERS: StatusFilter[] = [
  "all", "review_needed", "held_identity", "automatic", "released",
];

export function InboxPage() {
  const { language, navigate } = useAppState();
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<StatusFilter>("all");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(0);
  const [helpOpen, setHelpOpen] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setCases(await api.cases());
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    return cases.filter((item) => {
      const statusMatches = status === "all"
        || (status === "automatic" && item.status === "auto_decided")
        || item.status === status;
      const searchMatches = !needle || [
        item.id,
        item.applicant.name,
        item.applicant.organisation,
        item.question,
      ].join(" ").toLocaleLowerCase().includes(needle);
      return statusMatches && searchMatches;
    });
  }, [cases, query, status]);

  useEffect(() => {
    setSelected((index) => Math.min(index, Math.max(filtered.length - 1, 0)));
  }, [filtered.length]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const typing = target?.matches("input, textarea, select, [contenteditable='true']");
      if (typing) return;
      if (event.key === "/") {
        event.preventDefault();
        searchRef.current?.focus();
      } else if (event.key === "?") {
        event.preventDefault();
        setHelpOpen(true);
      } else if (event.key === "j" && filtered.length) {
        event.preventDefault();
        setSelected((index) => Math.min(index + 1, filtered.length - 1));
      } else if (event.key === "k" && filtered.length) {
        event.preventDefault();
        setSelected((index) => Math.max(index - 1, 0));
      } else if (event.key === "Enter" && filtered[selected]) {
        event.preventDefault();
        navigate(`/staff/case/${encodeURIComponent(filtered[selected].id)}`);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [filtered, navigate, selected]);

  const counts = useMemo(() => {
    const result: Record<StatusFilter, number> = {
      all: cases.length,
      review_needed: 0,
      held_identity: 0,
      automatic: 0,
      released: 0,
    };
    cases.forEach((item) => {
      if (item.status === "review_needed") result.review_needed += 1;
      if (item.status === "held_identity") result.held_identity += 1;
      if (item.status === "auto_decided") result.automatic += 1;
      if (item.status === "released") result.released += 1;
    });
    return result;
  }, [cases]);

  const filterLabel = (filter: StatusFilter) => {
    if (filter === "all") return t(language, "inbox.all");
    if (filter === "automatic") return t(language, "inbox.automatic");
    return t(language, `status.${filter}`);
  };

  return (
    <>
      <section aria-labelledby="page-title">
        <div className="page-toolbar">
          <h1 className="page-heading" id="page-title" tabIndex={-1}>{t(language, "title.inbox")}</h1>
          <Button kind="ghost" size="sm" onClick={() => setHelpOpen(true)}>
            {t(language, "keyboard.help")} · ?
          </Button>
        </div>
        <div className="page-toolbar">
          <div className="page-toolbar__filters" role="tablist" aria-label={t(language, "inbox.status")}>
            {FILTERS.map((filter) => (
              <Button
                key={filter}
                kind={status === filter ? "primary" : "tertiary"}
                size="sm"
                role="tab"
                aria-selected={status === filter}
                onClick={() => setStatus(filter)}
              >
                {filterLabel(filter)} <span className="filter-count">{counts[filter]}</span>
              </Button>
            ))}
          </div>
          <CarbonSearch
            id="case-search"
            labelText={t(language, "inbox.search")}
            placeholder={t(language, "inbox.search")}
            ref={searchRef}
            size="md"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>

        {loading || error ? (
          <PageState loading={loading} error={error} language={language} onRetry={load} />
        ) : filtered.length === 0 ? (
          <PageState empty={t(language, "inbox.empty")} language={language} />
        ) : (
          <>
            <div
              className="desktop-case-table table-scroll"
              role="region"
              aria-label={t(language, "title.inbox")}
              tabIndex={0}
            >
              <DataTable
                rows={filtered.map((item) => ({
                  id: item.id,
                  received: formatDateTime(item.received_at, language),
                  applicant: item.applicant.name,
                  kind: t(language, `kind.${item.kind}`),
                  decision: item.decision,
                  status: item.status,
                  safes: "",
                  ai: item.ai_involved ? t(language, "ai.on") : "",
                }))}
                headers={[
                  { key: "received", header: t(language, "inbox.received") },
                  { key: "id", header: t(language, "inbox.id") },
                  { key: "applicant", header: t(language, "inbox.applicant") },
                  { key: "kind", header: t(language, "inbox.kind") },
                  { key: "decision", header: t(language, "inbox.decision") },
                  { key: "status", header: t(language, "inbox.status") },
                  { key: "safes", header: t(language, "inbox.safes") },
                  { key: "ai", header: t(language, "inbox.ai") },
                ]}
                size="sm"
              >
                {({ headers, rows, getHeaderProps, getRowProps }) => (
                  <TableContainer aria-label={t(language, "title.inbox")}>
                    <Table size="sm">
                    <TableHead>
                      <TableRow>
                        {headers.map((header) => (
                          <TableHeader {...getHeaderProps({ header })}>
                            {header.header}
                          </TableHeader>
                        ))}
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {rows.map((row, index) => {
                        const item = filtered.find((record) => record.id === row.id);
                        if (!item) return null;
                        return (
                          <TableRow
                            {...getRowProps({ row })}
                            tabIndex={0}
                            aria-selected={selected === index}
                            onClick={() => setSelected(index)}
                            onDoubleClick={() => navigate(`/staff/case/${encodeURIComponent(item.id)}`)}
                            onKeyDown={(event) => {
                              if (event.key === "Enter") navigate(`/staff/case/${encodeURIComponent(item.id)}`);
                            }}
                          >
                            <TableCell>{formatDateTime(item.received_at, language)}</TableCell>
                            <TableCell className="mono">{item.id}</TableCell>
                            <TableCell>
                              <span>{item.applicant.name}</span>
                              <br />
                              <span className="secondary-text">{item.applicant.organisation}</span>
                            </TableCell>
                            <TableCell>{t(language, `kind.${item.kind}`)}</TableCell>
                            <TableCell><DecisionTag decision={item.decision} language={language} /></TableCell>
                            <TableCell><StatusTag status={item.status} language={language} /></TableCell>
                            <TableCell><SafeIndicators safes={item.five_safes} language={language} compact /></TableCell>
                            <TableCell>{item.ai_involved ? <Tag type="outline">KI</Tag> : "—"}</TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                    </Table>
                  </TableContainer>
                )}
              </DataTable>
            </div>
            <div className="mobile-case-list" aria-label={t(language, "title.inbox")}>
              {filtered.map((item) => (
                <button
                  className="mobile-case-row"
                  key={item.id}
                  onClick={() => navigate(`/staff/case/${encodeURIComponent(item.id)}`)}
                >
                  <span className="mobile-case-row__top">
                    <span className="mono">{item.id}</span>
                    <DecisionTag decision={item.decision} language={language} />
                    <StatusTag status={item.status} language={language} />
                  </span>
                  <strong>{item.applicant.name}</strong>
                  <span className="secondary-text">{item.applicant.organisation}</span>
                  <span className="secondary-text">{formatDateTime(item.received_at, language)}</span>
                  <SafeIndicators safes={item.five_safes} language={language} compact />
                </button>
              ))}
            </div>
          </>
        )}
      </section>
      <KeyboardHelp open={helpOpen} onClose={() => setHelpOpen(false)} language={language} />
    </>
  );
}
