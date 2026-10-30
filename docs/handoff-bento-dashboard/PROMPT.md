# Auftrag: Bento-Ergebnis-Dashboard in die Web-UI einbauen

> Prompt für die umsetzende KI (Claude Code / Codex) im Branch `track3-app`. Bitte vollständig lesen, dann nach
> dem Superpowers-Workflow aus `CLAUDE.md` vorgehen (Brainstorming, Spec-Ergänzung, Plan, TDD, Reviews,
> Verification). Doku auf Deutsch, alle UI-Texte auf Englisch.

## Rolle und Ziel

Du baust in der Web-UI von EHDS Access Desk („Doccess“) die **Ergebnisansicht für Antragsteller als Bento-Dashboard**.
Zielbild: `docs/handoff-bento-dashboard/screenshot-bento.png`; Maße/Farben: `bento-dashboard.html`.
Das Dashboard erscheint nach dem Absenden eines Antrags und zeigt Entscheidung, Rechtsgrundlage, Datenschutz,
Kennzahlen und das Ergebnis als Diagramm. Es ersetzt **keine** Logik: Es rendert ausschließlich die Felder, die die
Pipeline bereits liefert (`ProcessResult.applicant`, ausgewählte Kennzahlen aus `ProcessResult.staff`).

Voraussetzung: Task 11 (HTTP-API) liefert `POST /api/requests` (oder vergleichbar) mit `ProcessResult` als JSON.
Falls Task 11 noch offen ist: zuerst Task 11 abschließen, dann dieses Dashboard als Teil von Task 12.

## Harte Regeln (gelten zusätzlich zu `CLAUDE.md`)

1. **Nur freigegebene Werte darstellen.** Diagramm und Kacheln lesen nur `statistics.rows[].values` (bereits
   disclosed). Niemals Rohzahlen nachladen, nie Werte zurückrechnen, nie aus `"<10"` oder `"suppressed"` eine Zahl
   machen. Maskierte Zellen erscheinen als **schraffierter Platzhalter-Balken mit fester Mindesthöhe** und dem
   Label `<10` bzw. `suppressed`. Sie fließen nicht in die Skalierung ein.
2. **Keine Patienten-IDs**, keine Einzeldatensätze, auch nicht für SPE. Für SPE nur `patient_count` und die
   Zeilenzahlen je Tabelle (`spe.tables`).
3. **XSS-sicher:** DOM nur mit `textContent` und `createElement` bauen, kein `innerHTML` mit Antrags- oder
   Ergebnisdaten. Labels wie Regionsnamen und Metrik-Titel kommen aus Daten.
4. **CSP-tauglich und ohne CDN:** keine externen Skripte, Fonts oder Chart-Bibliotheken. Styles in einer eigenen
   CSS-Datei (kein `<style>` inline). Dynamische Balkenhöhen über `el.style.setProperty("--h", "62%")` (CSSOM ist
   CSP-konform).
5. **Barrierefrei:** Jede Kachel hat eine Überschrift. Das Diagramm hat `role="img"` mit `aria-label` als
   Zusammenfassung. Unter dem Diagramm gibt es einen Umschalter **„Chart / Table“**, und die Tabelle enthält
   dieselben Werte. Kontrast mindestens WCAG AA. Animationen nur bei `prefers-reduced-motion: no-preference`.
6. **Hinweis „Hackathon simulation · synthetic data · not a real approval system“** bleibt auf der Seite sichtbar
   (Challenge-Pflicht).

## Layout (aus dem Zielbild)

- Hintergrund `#eef1f5`. Grid mit 4 Spalten, `grid-auto-rows: 150px`, Abstand 14px, max. Breite 1200px, zentriert.
- Kachel: weiß, `border-radius: 26px`, Innenabstand 20px, Schatten `0 1px 2px #0001`.
- Kachel-Label: 11px, Großbuchstaben, `letter-spacing: .08em`, Farbe `#64748b`, fett.
- Große Zahl: 38px, Gewicht 800, `letter-spacing: -.03em`, Farbe `#0f172a`.
- Responsiv: unter 900px 2 Spalten, unter 600px 1 Spalte (Kacheln mit `span` fallen auf volle Breite).

| Kachel | Grid | Inhalt | Datenquelle |
|---|---|---|---|
| **Decision** | 2 Spalten × 2 Zeilen | Label `DECISION · CASE <id>`, Titel je Outcome (s. u.), ein Satz Begründung, Button **Decision letter (PDF)** (nur wenn ein Endpunkt existiert, sonst weglassen) | `decision`, `request_id`, `headline` (Fallback: `reasons[0]`) |
| **Privacy** | 1 × 2 | Ring (`conic-gradient`) mit `x/y`, darunter `checks passed`. Ohne Check-Liste im Backend: Ring = Anteil vollständig gezeigter Gruppen, Text `groups fully shown` | Check-Liste falls vorhanden, sonst `statistics.rows` (Zellen `<10`/`suppressed` zählen) |
| **Patients** | 1 × 1 | Anzahl berücksichtigter Patienten im Datensatz und `<n> opt-outs excluded` | neuer kleiner Endpunkt `GET /api/dataset` (Count `pat`, Differenz `pat_all − pat`), sonst `staff.opt_out_excluded` |
| **Answer time** | 1 × 1, dunkel (`#0f172a`, Text `#e2e8f0`) | `0.21 s` | `staff.timings_ms.total` / 1000, 2 Nachkommastellen |
| **Chart** | 3 × 2 | Titel `<METRIC LABEL> · PER <DIMENSION>` (Großbuchstaben), vertikale Balken mit Wert über dem Balken, Kurzlabel darunter (erste 3 Zeichen, volles Label als `title`/`aria`) | `statistics.metrics`, `statistics.dimensions`, `statistics.rows` |
| **Legal basis** | 1 × 1 | `Art. 53 · 69`, darunter `EHDS Regulation`; Hover/`title` zeigt die Artikeltitel | `articles`, `article_titles` |
| **Records released** | 1 × 1 | Statistik/REJECT: `0`; SPE: `0 downloadable`, Unterzeile `<n> patients in a secure workspace` | `decision`, `spe.patient_count` |

Balken: Verlauf `linear-gradient(180deg, #38bdf8, #0369a1)`, `border-radius: 12px 12px 4px 4px`. Die Höhe ist der
Wert geteilt durch den größten **numerischen** Wert der Metrik, mindestens 6 %, damit kleine Werte sichtbar bleiben.

## Diagramm-Regeln

- **Metrik-Auswahl:** Gibt es mehrere Metriken (z. B. count, count, percent), zuerst die letzte Prozent-Metrik
  zeigen, sonst die erste Count-Metrik. Darüber kleine Tabs mit allen Metriken.
- **Dimensionen:** Bei einer Dimension ist die x-Achse diese Dimension. Bei zwei oder mehr Dimensionen ist die
  x-Achse die erste. Für die übrigen gibt es ein Auswahlfeld (z. B. `Sex: female`), alternativ gruppierte Balken.
  Bei mehr als 12 Balken auf horizontale Balken umschalten, mit scrollbarem Bereich.
- **Format:** Prozent und Mittelwert immer mit einer Nachkommastelle (`8.0`, nicht `8`). Tausender mit schmalem
  Leerzeichen (`19 161`). Das Backend liefert Werte bereits gerundet, nicht neu runden.
- **Ein Satz über dem Diagramm** in einfacher Sprache, z. B. `Highest share: Tirol (8.9 %). All 9 groups are shown
  in full.` oder `3 of 9 groups are partly hidden because fewer than 10 patients were involved.`
- Für die Logik eine **reine Funktion** `chartModel(table, metricKey, filters)` schreiben. Sie liefert
  `[{label, shortLabel, value, display, masked, heightPct}]` und ist getrennt testbar.

## Zustände je Outcome

| Fall | Decision-Kachel | Chart-Kachel |
|---|---|---|
| `APPROVE_STATISTICAL` | grüner Verlauf `#ecfdf5 → #d1fae5`, Titel `Approved · anonymised statistics` (`#065f46`) | Diagramm wie oben, plus Button `Download anonymised statistics (CSV)` mit Hinweis `aggregated table only, no patient records` |
| `APPROVE_SPE` | blauer Verlauf, Titel `Approved · secure processing environment` | Kachel **Secure workspace**: große Zahl `patient_count`, horizontale Balken je Tabelle (`spe.tables`, Zeilenzahl), Badge `Downloads blocked (HTTP 403)` |
| `REJECT` | roter Verlauf (`#fef2f2 → #fee2e2`, Titel `#991b1b`), Titel `Request rejected`, Satz mit verbotenem Zweck und Artikel | Leerer Zustand: `No patient data was queried.` (kein Diagramm) |
| Manuelle Prüfung (Warnungen, `statistics` und `spe` leer) | amber, Titel `Needs a review by staff` | Liste der `notes`/Warnungen in Klartext |

## Tests und Abnahme

- **TDD:** zuerst Tests für `chartModel`. Prüfen:
  - maskierte Zellen haben `masked=true`, keine Zahl und gehen nicht in die Skalierung ein;
  - Prozentwerte haben eine Nachkommastelle;
  - die Metrik-Auswahl folgt der Regel oben;
  - bei mehr als 12 Gruppen ist `horizontal=true`.
- API-Test: Die JSON-Antwort für R01 enthält alle Felder, die das Dashboard braucht (Snapshot der Schlüssel).
- UI-Test im Browser (headless), Fälle R01, R05, R08 und R10:
  - richtige Kacheln je Fall;
  - R08 zeigt Platzhalter für `<10`/`suppressed`;
  - R10 zeigt kein Diagramm;
  - eine Region mit `<script>` im Namen wird als Text angezeigt;
  - bei 375px Breite gibt es kein horizontales Scrollen;
  - keine CSP- oder Konsolenfehler.
- **Abnahme:** Die Ansicht für R01 sieht aus wie `screenshot-bento.png`, mit denselben Werten
  (Tirol 8.9, Wien 8.1, Vorarlberg 5.6). Alle bestehenden Tests sind grün, `docs/STATUS.md`, `TODO.md` und
  `WORKLOG.md` sind gepflegt.

## Nicht-Ziele

Keine Änderungen an `decision.py`, `parsing/`, `disclosure.py` oder `spe.py`. Keine neuen Abhängigkeiten im
Frontend. Keine Daten aus `expected.json` in der UI.
