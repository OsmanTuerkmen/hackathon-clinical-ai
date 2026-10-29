import { de } from "./de";
import { en } from "./en";
import type { Language } from "../api/types";

export type TranslationKey = keyof typeof de;
const dictionaries: Record<Language, Record<TranslationKey, string>> = { de, en };

export const t = (language: Language, key: TranslationKey): string =>
  dictionaries[language][key];

export const locale = (language: Language): string =>
  language === "de" ? "de-AT" : "en-GB";

const numberLocale = (language: Language): string =>
  language === "de" ? "de-DE" : "en-GB";

export function formatDate(value: string | null | undefined, language: Language): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(locale(language), {
    dateStyle: "medium",
    timeZone: "UTC",
  }).format(date);
}

export function formatDateTime(value: string | null | undefined, language: Language): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(locale(language), {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: "UTC",
  }).format(date);
}

export function formatNumber(value: number, language: Language, decimals?: number): string {
  return new Intl.NumberFormat(numberLocale(language), {
    maximumFractionDigits: decimals ?? 1,
    minimumFractionDigits: decimals ?? 0,
  }).format(value);
}

export function formatCell(value: number | string, language: Language, type?: string): string {
  if (value === "suppressed") return t(language, "value.suppressed");
  if (value === "<10") return t(language, "value.lt10");
  if (typeof value === "string") return value;
  const formatted = formatNumber(value, language, type === "count" ? 0 : 1);
  return type === "pct" ? (language === "de" ? `${formatted} %` : `${formatted}%`) : formatted;
}
