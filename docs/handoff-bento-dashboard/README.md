# Übergabe: Bento-Ergebnis-Dashboard (für Task 12 „Web-UI“)

Stand 2026-10-30 · erstellt von Kaan (Branch `feature/track3-ehds-access-desk`) für den Branch `track3-app`.
Dieser Branch (`handoff/bento-dashboard`) basiert auf `track3-app` und fügt **nur** diesen Ordner hinzu.
`track3-app` selbst wurde nicht verändert.

## Worum es geht

Das Team hat sich für die UI von `track3-app` als Endprodukt entschieden. Die **Ergebnisansicht als Bento-Dashboard**
(Kacheln mit Entscheidung, Privacy-Ring, Kennzahlen und Balkendiagramm) aus Kaans Prototyp soll übernommen werden.
Sie macht das Ergebnis für Mediziner und die Jury auf einen Blick verständlich.

| Datei | Inhalt |
|---|---|
| `screenshot-bento.png` | Zielbild (Screenshot des Entwurfs, Statistik-Fall R01) |
| `bento-dashboard.html` | Statischer HTML/CSS-Entwurf, im Browser öffnen; Maße, Farben und Typografie zum Abgreifen |
| `PROMPT.md` | Verbindlicher Auftrag für die umsetzende KI, mit Datenzuordnung, Zuständen, Tests |
| `SUGGESTIONS.md` | Verbesserungsvorschläge für `track3-app`, die sich in Kaans Branch bewährt haben |

## Ansehen

```bash
git checkout handoff/bento-dashboard        # oder: git show handoff/bento-dashboard:docs/handoff-bento-dashboard/bento-dashboard.html > /tmp/b.html
start docs/handoff-bento-dashboard/bento-dashboard.html   # Windows; macOS: open …
```

Der Entwurf ist statisch: Die Zahlen sind die echten R01-Ergebnisse, nämlich der Anteil Erwachsener mit
Typ-2-Diabetes je Bundesland. Inline-Styles gibt es nur im Entwurf. In der App müssen die Styles CSP-tauglich in
einer eigenen CSS-Datei liegen (siehe `PROMPT.md`).

## Einordnung im Plan

- Gehört zu **Task 12 (Web-UI)**, Ansicht des Antragstellers nach dem Absenden. Es braucht die HTTP-API aus Task 11.
- Datenquelle sind die vorhandenen Modelle aus `src/ehds_desk/pipeline.py`:
  - `ApplicantView`: `decision`, `articles`, `article_titles`, `headline`, `reasons`, `statistics`, `spe`, `notes`
  - aus `StaffView`: `timings_ms.total` und `opt_out_excluded`
- An Entscheidungslogik, Parser oder Disclosure ändert sich nichts. Das Dashboard **stellt nur dar**, was die
  Pipeline freigegeben hat.

## Merge-Hinweis

Der Ordner ist in sich geschlossen. Ein Merge von `handoff/bento-dashboard` in `track3-app` verursacht keine
Konflikte. Alternativ übernimmt man nur den Ordner:
`git checkout handoff/bento-dashboard -- docs/handoff-bento-dashboard`.
