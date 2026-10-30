import {
  ChartColumn,
  CheckmarkFilled,
  CheckmarkOutline,
  CircleDash,
  Locked,
  Misuse,
  WarningAltFilled,
} from "@carbon/icons-react";
import {
  Button,
  InlineLoading,
  InlineNotification,
  Modal,
  Select,
  SelectItem,
  Tag,
} from "@carbon/react";
import { max as maxValue } from "d3-array";
import { geoMercator, geoPath } from "d3-geo";
import { scaleThreshold } from "d3-scale";
import { useMemo, useState, type ReactNode } from "react";
import type { FeatureCollection, Geometry } from "geojson";
import regions from "../assets/austria-states.json";
import type {
  CaseSummary,
  CellValue,
  FunnelStep,
  Language,
  PersonFlag,
  PipelineResult,
  ReleasedTable,
  SafeName,
  SafeStatus,
} from "../api/types";
import { formatCell, formatDateTime, formatNumber, t } from "../i18n";

const STATUS_ICONS: Record<SafeStatus, typeof CheckmarkFilled> = {
  pass: CheckmarkFilled,
  warn: WarningAltFilled,
  fail: Misuse,
  na: CircleDash,
};

const SAFE_NAMES: SafeName[] = ["people", "projects", "data", "settings", "outputs"];

export function StatusTag({
  status,
  language,
}: {
  status: CaseSummary["status"];
  language: Language;
}) {
  const type = status === "rejected_after_review"
    ? "red"
    : status === "released"
      ? "green"
      : status === "held_identity" || status === "review_needed"
        ? "warm-gray"
        : "cool-gray";
  const warning = status === "held_identity" || status === "review_needed";
  return (
    <Tag type={type} className={warning ? "accessdesk-tag--held" : undefined}>
      {warning && <WarningAltFilled size={16} aria-hidden="true" />}
      {status === "released" && <CheckmarkOutline size={16} aria-hidden="true" />}
      {t(language, `status.${status}`)}
    </Tag>
  );
}

export function DecisionTag({
  decision,
  language,
}: {
  decision: CaseSummary["decision"];
  language: Language;
}) {
  const type = decision === "REJECT" ? "red" : decision === "APPROVE_SPE" ? "teal" : "green";
  const Icon = decision === "REJECT" ? Misuse : decision === "APPROVE_SPE" ? Locked : ChartColumn;
  return <Tag type={type}><Icon size={16} aria-hidden="true" />{t(language, `decision.${decision}`)}</Tag>;
}

export function SafeIndicators({
  safes,
  language,
  compact = false,
}: {
  safes: Record<SafeName, SafeStatus>;
  language: Language;
  compact?: boolean;
}) {
  return (
    <div className={`safe-indicators${compact ? " safe-indicators--compact" : ""}`}>
      {SAFE_NAMES.map((name) => {
        const status = safes[name];
        const Icon = STATUS_ICONS[status];
        const label = `${t(language, `safe.${name}`)}: ${t(language, `safe.${status}`)}`;
        return (
          <span
            className={`safe-indicator safe-indicator--${status}`}
            key={name}
            title={label}
            aria-label={label}
          >
            <Icon size={16} aria-hidden="true" />
            {!compact && <span>{t(language, `safe.${name}`)}: {t(language, `safe.${status}`)}</span>}
            {compact && <span className="visually-hidden">{label}</span>}
          </span>
        );
      })}
    </div>
  );
}

export function ValueCell({
  value,
  language,
  type,
  footnote = false,
}: {
  value: CellValue;
  language: Language;
  type?: string;
  footnote?: boolean;
}) {
  const hidden = value === "<10" || value === "suppressed";
  return (
    <span className={`value-cell${hidden ? " value-cell--hidden" : ""}`}>
      {hidden
        ? <span className="value-chip">{formatCell(value, language, type)}{footnote && <sup>1</sup>}</span>
        : formatCell(value, language, type)}
    </span>
  );
}

export function ResultTable({
  released,
  language,
  emptyMessage,
}: {
  released: ReleasedTable | null;
  language: Language;
  emptyMessage?: string;
}) {
  if (!released || released.rows.length === 0) {
    return <p className="secondary-text">{emptyMessage ?? t(language, "case.noResults")}</p>;
  }
  const types = Object.fromEntries(released.measures.map((measure) => [measure.key, measure.type]));
  return (
    <div className="table-scroll" role="region" aria-label={t(language, "case.tab.result")} tabIndex={0}>
      <table className="data-table" aria-label={t(language, "case.tab.result")}>
        <thead>
          <tr>
            {released.group_dims.map((dimension, index) => (
              <th key={`${dimension}-${index}`} scope="col">{groupDimensionLabel(dimension, language)}</th>
            ))}
            {released.measures.map((measure) => (
              <th key={measure.key} className="data-table__number" scope="col">
                {measureLabel(measure.label)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {released.rows.map((row, rowIndex) => (
            <tr key={`${row.group.join("|")}-${rowIndex}`}>
              {row.group.map((value, index) => (
                <td key={`${released.group_dims[index]}-${value}`}>{value}</td>
              ))}
              {released.measures.map((measure) => (
                <td className="data-table__number" key={measure.key}>
                  <ValueCell
                    value={row.values[measure.key] ?? "suppressed"}
                    language={language}
                    type={types[measure.key]}
                    footnote={Boolean(released.differencing?.suppressed.some(
                      (item) => item.measure === measure.key
                        && item.group.join("|") === row.group.join("|"),
                    ))}
                  />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Funnel({
  steps,
  language,
}: {
  steps: FunnelStep[];
  language: Language;
}) {
  const numeric = steps.map((step) => typeof step.count === "number" ? step.count : 10);
  const maximum = Math.max(...numeric, 1);
  if (steps.length === 0) return null;
  return (
    <div className="funnel-list" aria-label={t(language, "case.funnel")}>
      {steps.map((step) => {
        const hidden = typeof step.count === "string";
        const count = typeof step.count === "string"
          ? step.count
          : formatNumber(step.count, language, 0);
        const width = Math.max((numeric[steps.indexOf(step)] / maximum) * 100, hidden ? 2 : 0);
        return (
          <div className="funnel-step" key={step.key}>
            <span>{language === "de" ? step.label_de : step.label_en}</span>
            <div className={`funnel-track${hidden ? " value-cell--hidden" : ""}`}>
              <div
                className={`funnel-fill${hidden ? " funnel-fill--hidden" : ""}`}
                style={{ width: `${width}%` }}
              />
            </div>
            <span className="funnel-count">{count}</span>
          </div>
        );
      })}
    </div>
  );
}

export function EvidenceText({
  text,
  field,
  evidence,
  category = "allowed",
}: {
  text: string;
  field: string;
  evidence: Array<{
    phrase: string;
    field: string;
    start: number;
    end: number;
    category?: "prohibited" | "allowed" | "justification";
  }>;
  category?: "prohibited" | "allowed" | "justification";
}) {
  const ranges = evidence
    .filter((item) => item.field === field && item.start >= 0 && item.end <= text.length)
    .sort((left, right) => left.start - right.start || right.end - left.end);
  const pieces: ReactNode[] = [];
  let cursor = 0;
  ranges.forEach((item, index) => {
    if (item.start < cursor) return;
    if (item.start > cursor) pieces.push(text.slice(cursor, item.start));
    pieces.push(
      <mark data-category={item.category ?? category} key={`${item.start}-${item.end}-${index}`}>
        {text.slice(item.start, item.end)}
      </mark>,
    );
    cursor = item.end;
  });
  if (cursor < text.length) pieces.push(text.slice(cursor));
  return <>{pieces}</>;
}

export function KeyboardHelp({
  open,
  onClose,
  language,
}: {
  open: boolean;
  onClose: () => void;
  language: Language;
}) {
  return (
    <Modal
      open={open}
      modalHeading={t(language, "keyboard.help")}
      primaryButtonText={t(language, "review.cancel")}
      secondaryButtonText=""
      onRequestClose={onClose}
      onRequestSubmit={onClose}
      onSecondarySubmit={onClose}
      size="sm"
    >
      <dl className="shortcut-list">
        <div><dt>j / k</dt><dd>{t(language, "keyboard.next")} / {t(language, "keyboard.previous")}</dd></div>
        <div><dt>Enter</dt><dd>{t(language, "keyboard.open")}</dd></div>
        <div><dt>/</dt><dd>{t(language, "keyboard.search")}</dd></div>
        <div><dt>?</dt><dd>{t(language, "keyboard.help")}</dd></div>
      </dl>
    </Modal>
  );
}

export function ResultChart({
  released,
  language,
  measureIndex = 0,
}: {
  released: ReleasedTable | null;
  language: Language;
  measureIndex?: number;
}) {
  if (!released || released.rows.length === 0) return null;
  if (released.group_dims.length !== 1) return null;
  const dimension = released.group_dims[0];
  const firstPercent = released.measures.findIndex((item) => item.type === "pct");
  const firstMean = released.measures.findIndex((item) => item.type === "mean");
  const preferred = firstPercent >= 0 ? firstPercent : firstMean >= 0 ? firstMean : 0;
  if (dimension === "region") {
    return <AustriaMap released={released} language={language} measureIndex={preferred} />;
  }
  return <BarChart released={released} language={language} measureIndex={preferred} />;
}

export function BarChart({
  released,
  language,
  measureIndex = 0,
}: {
  released: ReleasedTable;
  language: Language;
  measureIndex?: number;
}) {
  const measure = released.measures[measureIndex] ?? released.measures[0];
  if (!measure) return null;
  const values = released.rows.map((row) => row.values[measure.key] ?? "suppressed");
  const numeric = values.map((value) => typeof value === "number" ? value : 10);
  const max = Math.max(...numeric, 1);
  const width = 760;
  const rowHeight = 38;
  const labelWidth = 180;
  const chartWidth = 500;
  const height = Math.max(180, released.rows.length * rowHeight + 36);
  return (
    <figure className="chart-frame">
      <svg className="chart-svg" viewBox={`0 0 ${width} ${height}`} role="img" aria-labelledby="bar-chart-title bar-chart-desc">
        <title id="bar-chart-title">{measureLabel(measure.label)}</title>
        <desc id="bar-chart-desc">
          {language === "de" ? "Balkendiagramm nach Gruppe." : "Bar chart by group."}
        </desc>
        <defs>
          <pattern id="small-cell-hatch" width="6" height="6" patternTransform="rotate(45)" patternUnits="userSpaceOnUse">
            <line x1="0" y1="0" x2="0" y2="6" className="map-hatch-line" />
          </pattern>
        </defs>
        {released.rows.map((row, index) => {
          const value = values[index];
          const hidden = typeof value === "string";
          const length = (numeric[index] / max) * chartWidth;
          const y = index * rowHeight + 20;
          return (
            <g key={`${row.group.join("|")}-${index}`}>
              <text x="0" y={y + 17} className="chart-label">{row.group.join(" · ")}</text>
              {hidden ? (
                <rect
                  className="chart-bar--hidden"
                  x={labelWidth}
                  y={y}
                  width={Math.max(length, 10)}
                  height="24"
                />
              ) : (
                <rect
                  className="chart-bar"
                  x={labelWidth}
                  y={y}
                  width={Math.max(length, 2)}
                  height="24"
                />
              )}
              <text x={labelWidth + Math.max(length, 10) + 8} y={y + 17} className="chart-value">
                {formatCell(value, language, measure.type)}
              </text>
            </g>
          );
        })}
      </svg>
      <figcaption className="chart-frame__legend">
        <span className="hatch-legend">
          <span className="hatch-swatch" aria-hidden="true" />
          {t(language, "chart.legend")}
        </span>
      </figcaption>
    </figure>
  );
}

interface AustriaProperties {
  region: string;
  iso_3166_2: string;
}

export function AustriaMap({
  released,
  language,
  measureIndex = 0,
}: {
  released: ReleasedTable;
  language: Language;
  measureIndex?: number;
}) {
  const measures = released.measures;
  const [selected, setSelected] = useState(measureIndex);
  const measure = measures[selected] ?? measures[0];
  const collection = regions as FeatureCollection<Geometry, AustriaProperties>;
  const projection = useMemo(() => geoMercator().fitSize([720, 470], collection), [collection]);
  const path = useMemo(() => geoPath(projection), [projection]);
  const values = new Map(
    released.rows.map((row) => [
      row.group[0] ?? "",
      row.values[measure.key] ?? "suppressed",
    ] as const),
  );
  const numeric = [...values.values()].filter((value): value is number => typeof value === "number");
  const max = maxValue(numeric) ?? 1;
  const thresholds = [0.2, 0.4, 0.6, 0.8].map((fraction) => max * fraction);
  const color = scaleThreshold<number, string>()
    .domain(thresholds)
    .range([
      "var(--accessdesk-map-bin-1)",
      "var(--accessdesk-map-bin-2)",
      "var(--accessdesk-map-bin-3)",
      "var(--accessdesk-map-bin-4)",
      "var(--accessdesk-map-bin-5)",
    ]);
  return (
    <figure className="chart-frame">
      {measures.length > 1 && (
        <div className="chart-measure">
          <Select
            id="chart-measure"
            labelText={t(language, "chart.measure")}
            size="sm"
            value={selected}
            onChange={(event) => setSelected(Number(event.target.value))}
          >
            {measures.map((item, index) => (
              <SelectItem key={item.key} value={index} text={measureLabel(item.label)} />
            ))}
          </Select>
        </div>
      )}
      <svg className="chart-svg" viewBox="0 0 720 470" role="img" aria-labelledby="austria-map-title austria-map-desc">
      <title id="austria-map-title">{measureLabel(measure.label)}</title>
        <desc id="austria-map-desc">
          {language === "de" ? "Karte der neun österreichischen Bundesländer." : "Map of the nine Austrian states."}
        </desc>
        <defs>
          <pattern id="small-cell-hatch" width="6" height="6" patternTransform="rotate(45)" patternUnits="userSpaceOnUse">
            <line x1="0" y1="0" x2="0" y2="6" className="map-hatch-line" />
          </pattern>
        </defs>
        {collection.features.map((feature) => {
          const region = feature.properties.region;
          const value = values.get(region) ?? "suppressed";
          const hidden = typeof value === "string";
          const centroid = path.centroid(feature);
          const isVienna = feature.properties.iso_3166_2 === "AT-9";
          const labelX = centroid[0] + (isVienna ? 28 : 0);
          const labelY = centroid[1] + (isVienna ? 16 : 0);
          return (
            <g key={feature.properties.iso_3166_2}>
              <path
                d={path(feature) ?? ""}
                className={`map-region${hidden ? " map-region--hidden" : ""}`}
                fill={hidden ? "url(#small-cell-hatch)" : color(value)}
              >
                <title>{`${region}: ${formatCell(value, language, measure.type)}`}</title>
              </path>
              {isVienna && (
                <line x1={centroid[0]} y1={centroid[1]} x2={labelX - 4} y2={labelY - 4} className="map-leader" />
              )}
              <text x={labelX} y={labelY} className="map-label">
                {formatCell(value, language, measure.type)}
              </text>
            </g>
          );
        })}
      </svg>
      <figcaption className="chart-frame__legend">
        <span className="map-color-legend" aria-label={language === "de" ? "Farbskala" : "Colour scale"}>
          {[
            [0, thresholds[0]],
            [thresholds[0], thresholds[1]],
            [thresholds[1], thresholds[2]],
            [thresholds[2], thresholds[3]],
            [thresholds[3], max],
          ].map(([from, to], index) => (
            <span className="map-color-bin" key={index}>
              <span className={`map-color-swatch map-color-swatch--${index + 1}`} aria-hidden="true" />
              {`${formatNumber(from, language, 0)}–${formatNumber(to, language, 0)}`}
            </span>
          ))}
        </span>
        <span className="hatch-legend">
          <span className="hatch-swatch" aria-hidden="true" />
          {t(language, "chart.legend")}
        </span>
      </figcaption>
    </figure>
  );
}

export function measureLabel(label: string): string {
  const cleaned = label.replace(/^(?:the|a|an|number of)\s+/i, "").trim();
  return cleaned ? cleaned[0].toLocaleUpperCase() + cleaned.slice(1) : label;
}

export function PageState({
  loading,
  error,
  empty,
  language,
  onRetry,
}: {
  loading?: boolean;
  error?: string | null;
  empty?: string | null;
  language: Language;
  onRetry?: () => void;
}) {
  if (loading) {
    return (
      <div className="state-view" role="status">
        <InlineLoading description={t(language, "loading")} />
      </div>
    );
  }
  if (error) {
    return (
      <>
        <InlineNotification
          kind="error"
          lowContrast
          title={t(language, "error.title")}
          subtitle={error}
        />
        {onRetry && (
          <Button kind="tertiary" size="sm" onClick={onRetry}>
            {t(language, "error.retry")}
          </Button>
        )}
      </>
    );
  }
  if (empty) return <div className="state-view">{empty}</div>;
  return null;
}

export function PlaceholderIcon({ status }: { status: SafeStatus }) {
  const Icon = STATUS_ICONS[status];
  return <Icon size={16} aria-hidden="true" />;
}

export function StatusIcon({ decision }: { decision: string }) {
  if (decision === "APPROVE_SPE") return <Locked size={16} aria-hidden="true" />;
  if (decision === "REJECT") return <Misuse size={16} aria-hidden="true" />;
  return <ChartColumn size={16} aria-hidden="true" />;
}

export function GroupLabel({ value, language }: { value: string; language: Language }) {
  return <>{groupDimensionLabel(value, language)}</>;
}

export function groupDimensionLabel(value: string, language: Language): string {
  const labels: Record<string, string> = {
    region: language === "de" ? "Bundesland" : "Region",
    data_holder: language === "de" ? "Klinikum" : "Hospital",
    sex: language === "de" ? "Geschlecht" : "Sex",
    age_band: language === "de" ? "Altersgruppe" : "Age band",
    year: language === "de" ? "Jahr" : "Year",
    g_region: language === "de" ? "Bundesland" : "Region",
    g_data_holder: language === "de" ? "Klinikum" : "Hospital",
    g_sex: language === "de" ? "Geschlecht" : "Sex",
    g_age_band: language === "de" ? "Altersgruppe" : "Age band",
    g_year: language === "de" ? "Jahr" : "Year",
  };
  return labels[value] ?? value;
}

export function FiveSafeStatus({ status, language }: { status: SafeStatus; language: Language }) {
  const Icon = STATUS_ICONS[status];
  return (
    <span className={`safe-indicator safe-indicator--${status}`}>
      <Icon size={16} aria-hidden="true" />
      {t(language, `safe.${status}`)}
    </span>
  );
}
