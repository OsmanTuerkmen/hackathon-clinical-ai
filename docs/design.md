# AccessDesk 2 – Design decisions

The app is a working tool for a health data access body and for the researchers who apply to it. It should look like GOV.UK, NHS.UK, IBM Carbon or Linear: typography carries the hierarchy, real data appears on every screen, tables are dense, and there is no decoration. Anything that looks like a marketing page is wrong.

## 1. Foundation

- **Design system:** IBM Carbon v11 (`@carbon/react`, `@carbon/icons-react`), themes **White** (light) and **G100** (dark), switchable and stored in localStorage. The first visit follows `prefers-color-scheme`.
- **Fonts:** IBM Plex Sans for UI text, IBM Plex Mono for codes, SQL, IDs and hashes. Bundled locally; the app makes **no external network request** at runtime (fonts, GeoJSON and icons are all local).
- **Tokens only:** colours, spacing and type come from Carbon tokens (`$text-primary`, `$layer-01`, `$spacing-05`, `heading-03` …). App-specific tokens such as the status colours and the hatch pattern live in one SCSS partial `web/src/styles/_tokens.scss` and are referenced by name. Components contain no raw hex values.
- **Grid:** Carbon's 2x grid, 8 px base, 4 px steps for fine spacing. Content max width 1584 px.
- **One accent colour:** Carbon interactive blue (`$interactive`, `$button-primary`). It is used only for primary actions, links, focus, selection and the data scale in charts.

## 2. Status colours (meaning only, always with icon and text)

| Meaning | DE / EN label | Colour | Icon (@carbon/icons-react) |
|---|---|---|---|
| Refused (Art. 54) | Abgelehnt / Refused | red, `$support-error` | `Misuse` |
| Approved as statistics | Statistik / Statistics | green, `$support-success` | `ChartColumn` |
| Approved for SPE (data permit) | SPE-Zugang / SPE access | teal (Carbon teal 60 / teal 40 in G100) | `Locked` |
| Held (review needed or identity) | Zurückgehalten / On hold | yellow, `$support-warning`, with dark text | `WarningAltFilled` |

Case status (inbox): `auto_decided` = "Automatisch entschieden / Decided automatically", `review_needed` = "Prüfung nötig / Review needed", `held_identity` = "Identität offen / Identity pending", `released` = "Freigegeben / Released", `rejected_after_review` = "Nach Prüfung abgelehnt / Refused after review". The decision tag and the status tag are separate columns. Colour never carries meaning on its own.

Five Safes indicators use `pass` (green `CheckmarkFilled`), `warn` (yellow `WarningAltFilled`), `fail` (red `Misuse`) and `na` (grey `CircleDash`), each with a text label or tooltip and an aria-label.

## 3. Hidden values (small-cell rule)

- Table cells with `<10` or `suppressed` get a diagonal hatch (45°, 1 px lines every 6 px in `$border-strong`). The text stays readable: "<10" or "unterdrückt / suppressed" in `$text-secondary`.
- Charts use the same hatch as an SVG `<pattern>`. A suppressed count is drawn as a hatched bar from 0 to 10 labelled "<10". Its length is the range of possible values, not a value. A suppressed share or mean gets a hatched stub labelled "unterdrückt". On the map, hatched states are labelled "<10" or "unterdrückt".
- Every chart has a one-line legend ("Schraffiert: verborgen nach der Small-Cell-Regel") and the same data as a table next to it or below it. The table is the accessible source of truth.
- No total rows and no sums anywhere, not even in charts.

## 4. Typography

- Page title: Carbon `heading-04` (28/36). Section: `heading-03`. Sub-section: `heading-02`. Body: `body-01`. Tables and dense UI: `body-compact-01`. Labels and table headers: `label-01`/`heading-compact-01`.
- Numbers use `font-variant-numeric: tabular-nums` (all numeric cells, metrics, counts) and are right-aligned in tables. German formatting in DE (1.152 · 8,3 %), English in EN (1,152 · 8.3%).
- Sentence case everywhere. Headings are never italic. Line length at most about 80 characters in running text.

## 5. Information architecture (hash routes)

```
#/staff/inbox            Eingang / Inbox (default)
#/staff/case/:id         Fall / Case (Five Safes)
#/staff/exports          Ausgabeprüfung / Output review
#/staff/audit            Prüfprotokoll / Audit log
#/staff/eval             Auswertung / Evaluation
#/apply/new              Neuer Antrag / New application (builder with pre-check)
#/apply/cases            Meine Anträge / My applications
#/apply/case/:id         Ergebnis / Result
#/apply/spe/:permit      SPE-Arbeitsbereich / SPE workspace
#/register               Transparenzregister / Transparency register (public)
#/letter/:id             Bescheid / Decision letter (print layout)
```

- **Header** (Carbon UI Shell): "AccessDesk", then the subtitle "Zugangsstelle für Gesundheitsdaten · Demo". It also holds the role switch (Behörde · Antragsteller · Öffentlich), DE/EN, the light/dark toggle and the AI status ("KI aus" / "KI an"). On mobile these move into the header menu.
- **Staff** have a left side nav: Eingang, Ausgabeprüfung, Prüfprotokoll, Auswertung. Below 1056 px it collapses into a rail or menu.
- **Applicant:** "Angemeldet als …" with a demo eID picker (simulated ID Austria / EUDI Wallet) in the page header of the applicant area.
- After every route change, focus moves to the page `h1`. A "Zum Inhalt springen" skip link is provided.

## 6. Screens

**Inbox.** Dense DataTable (`size="sm"`). Columns:
- Eingang (date and time)
- ID
- Antragsteller:in, with the organisation below in `$text-secondary`
- Art (Anfrage Art. 69 / Antrag Art. 67)
- Entscheidung (status tag and articles)
- Status
- Five Safes (5 mini indicators)
- KI (marker if AI was involved)

The toolbar has search and status tabs with real counts (Alle · Prüfung nötig · Identität offen · Automatisch · Freigegeben). Keys: `j`/`k` move the selection (`aria-selected`), `Enter` opens the case, `/` focuses the search, `?` opens the shortcut help. Below 672 px the table becomes a compact list.

**Case (Five Safes).** The header shows ID, applicant, organisation, received date, decision tag, articles with titles, status, and the primary action "Prüfen" (review). Below it comes the **Five Safes overview**, a 5-row table: Safe · question · status · finding · link to the evidence.

| Safe | DE question | EN question |
|---|---|---|
| Safe People | Wer fragt? | Who is asking? |
| Safe Projects | Wozu? | For what purpose? |
| Safe Data | Welche Daten? | Which data? |
| Safe Settings | Wo wird gerechnet? | Where is it processed? |
| Safe Outputs | Was verlässt die Stelle? | What leaves the access body? |

Tabs:
- **Antrag:** the request text, with evidence phrases highlighted by `<mark>` plus a category label (prohibited red underline, allowed green, justification teal); the definitions as a numbered list.
- **Entscheidung:** the rule trace for steps 1–4 (yes/no and evidence), the articles with official titles, and the AI second opinion if one exists.
- **Daten:** term → code table (term, system, code, label, rows), the query plan summary, the generated SQL (`CodeSnippet`, Plex Mono), the exact cohort funnel, and the 839 opt-outs excluded.
- **Ergebnis:** the released table plus chart, and the gate log (cells, hidden counts, suppressed values).
- **Umgebung:** for an SPE, the permit manifest (tables copied and not copied with row counts, persons, expiry) and a link to the workspace. For statistics: "processed inside the access body".
- **Personen:** the identity checks (person, organisation, mandate, role) with issuer and signature result, plus plausibility flags.
- **Protokoll:** the audit entries of the case.

The **review modal** has the actions Freigeben / Zurückhalten / Ablehnen (radio), a mandatory reason (at least 20 characters, live counter, error next to the field) and the reviewer name. A successful save updates the status in place without a toast.

**Builder (applicant).** On desktop it has two columns: the form on the left and the live pre-check on the right (sticky). On mobile they stack.
- **Form:**
  - "Ihre Frage" (free text) with the button "Entwurf erstellen". With AI it fills the fields, without AI it is disabled with a one-line reason.
  - Templates (Prävalenz nach Bundesland, Mittelwert nach Klinikum, Stationäre Aufenthalte nach Hauptdiagnose, Behandlungslücke nach Altersgruppe, Einzeldaten in der SPE).
  - Art (radio: Gesundheitsdatenanfrage → Statistik, Art. 69 / Antrag auf Zugang → Einzeldaten in der SPE, Art. 67), Zweck, Frage, and Definitionen (a list with add and remove).
  - A JSON toggle to paste or view the raw request. The jury can paste any request JSON there.
- **Pre-check** (debounced 400 ms):
  - the expected decision (tag, articles and one sentence)
  - **Art. 54 warnings with the quoted phrase, before submitting**
  - term → code (with row counts, protected: "<10" or rounded to 10)
  - expected cohort size (protected, labelled "gerundet")
  - the expected result shape (groups × measures without numbers)
  - parser warnings
  - identity status

**Result (applicant).** A plain-language decision banner, the reason, and the articles with titles. Then the table and chart, chosen like this:
- region → Austria map
- age band, hospital, sex or year → bars
- two dimensions → table only

The protected funnel follows, then the "Bescheid öffnen" button and, for an SPE, "Zum SPE-Arbeitsbereich". Held cases show "In Prüfung" with the reason and no numbers.

**SPE workspace.** The header shows permit ID, expiry and authorised persons. A table list (cohort, conditions, …) shows row counts. Then:
- the SQL console (Plex Mono textarea, `Ctrl+Enter` runs, results limited to 200 rows)
- "Export zur Prüfung einreichen" (title and note, then the automatic check result)
- "Rohdaten herunterladen", which shows the 403 block as an error notification: "Download blockiert (Art. 73 Abs. 2). Der Versuch wurde protokolliert."
- the list of own export requests. Approved ones can be downloaded as CSV.

**Output review (staff).** A table of export requests (permit, applicant, title, created, automatic check, status) with a detail preview. Approve or reject requires a reason.

**Audit log.** A table (seq, time, actor, action, case, summary, hash prefix in Plex Mono). The "Kette prüfen" button shows "Kette intakt: N Einträge" or "Bruch bei Eintrag N: …".

**Evaluation.** The "Auswertung starten" button produces the five metrics with target and result, the per-request table, and the strict oracle suite.

**Transparency register (public).** One row per request: received date, reference, organisation, type, purpose, decision and articles, justification (expandable), and the permit (duration, record types). The legal basis is shown at the top: Art. 57(1)(j)(ii)–(iii) and Art. 58(1)(f). No numbers, no persons' names, no identity-check details.

**Decision letter.** A4 print layout (`@page { size: A4; margin: 20mm }`). When printing, the app chrome is hidden and the text is black. It contains:
- the authority block, reference and date, the applicant and the subject
- Spruch, Begründung (numbered) and Auflagen (numbered)
- the annex: the result table, or the permit details
- Rechtsmittelbelehrung, visibly marked as a demo placeholder
- signature and checksum, and the demo notice
- held cases carry the "ENTWURF" notice

The buttons "Drucken / Als PDF speichern" (`window.print()`) and DE/EN are not printed.

## 7. Charts

- The **Austria map** uses d3-geo with local GeoJSON of the 9 Bundesländer (Natural Earth admin-1, public domain, matched by ISO 3166-2 codes AT-1…AT-9). It is a choropleth in steps of the accent hue (5 bins), with hatched suppressed states. Every state is labelled with its value, and a measure picker appears if there are several measures.
- **Bars** are horizontal, carry value labels and use a single colour (accent). They are drawn with d3-scale and plain SVG.
- The **funnel** is a set of horizontal steps with bar length proportional to the count. Applicants see protected counts, staff see exact ones.
- There is no animation beyond Carbon's defaults. Hover tooltips are optional, and everything is readable without hover.

## 8. States, keyboard, accessibility

- Every data view has loading (Carbon skeletons), empty (one sentence about what to do) and error (inline notification with retry) states.
- Full keyboard use: visible focus, no keyboard traps, and the shortcuts above do not fire while typing in inputs.
- WCAG 2.1 AA in both themes. The yellow tag uses dark text. Charts have `<title>`/`<desc>` and an adjacent table. Icons are decorative (`aria-hidden`) when text is next to them.
- Responsive from 390 px: no page-level horizontal scroll (`overflow-x: clip` on html/body). Wide tables scroll inside their own container, and clickable text stays on one line.
- `prefers-reduced-motion` is respected.

## 9. AI marking

Wherever AI contributed (a drafted definition, the purpose second opinion, a term → code suggestion), a small outline tag "KI-Vorschlag / AI suggestion" appears with a toggletip. The toggletip states the model, what the AI proposed, and **what was checked afterwards** (for example "Codes aus der Liste der Codes in den Daten validiert; Entscheidung durch Regeln"). Carbon's AI gradient and glow container styles are not used. Without an API key, the header shows "KI aus" and the AI buttons are disabled with a one-line reason.

## 10. Copy

- Short, precise and factual, with the same terms everywhere:
  - Gesundheitsdatenanfrage (Art. 69)
  - Antrag auf Zugang zu Gesundheitsdaten (Art. 67)
  - Datengenehmigung
  - sichere Verarbeitungsumgebung (SPE)
  - Zugangsstelle
  - Widerspruch / Opt-out (Art. 71)
- Use these EN terms: health data request, health data access application, data permit, secure processing environment, access body, opt-out.
- No marketing words ("powerful", "seamless", "AI-powered"), no emojis, no exclamation marks.
- DE and EN are complete. The dictionaries are typed so that a missing key fails the build.

## 11. Banned

- Gradients, glassmorphism and glow
- Emoji icons and "✨ AI"
- Hero sections, marketing text and card grids for everything
- Rounded-2xl with shadows
- The shadcn/Tailwind default look
- Invented numbers or charts, and lorem ipsum
- More than one accent colour
- Animation without a purpose
- Italic headings
- Redrawn browser or window chrome
