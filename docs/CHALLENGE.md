# Challenge: Clinical AI Hackathon (AIM Austria) – Track 3 „European Health Data Space“

Quelle: `../track3/README.md`, `../track3/data/README.md` (nicht im Repo), verbindlicher Auftrag: `docs/PROMPT_track3.md`.

## Aufgabe

In jedem EU-Land entscheidet eine Health Data Access Body über Anträge auf Sekundärnutzung von Gesundheitsdaten.
Gebaut wird eine App, die einen Antrag (JSON) automatisch:
1. entscheidet: `REJECT`, `APPROVE_STATISTICAL` oder `APPROVE_SPE`, mit Artikeln (Leiter siehe `docs/LAW.md`);
2. für Statistik die Zahlen aus den Daten mit Small-Cell-Regel berechnet;
3. für eine SPE die Datensätze der ausgewählten Patienten (nur genannte Record-Typen, Patienten-IDs behalten) in eine
   abgeschottete Umgebung kopiert, die exakte Patientenzahl meldet und Downloads blockiert;
4. Entscheidung und Begründung für Antragsteller und Personal anzeigt.

## Daten

20.000 synthetische Patienten aus drei Kliniken (Klinikum Nord/Süd/West), fünf CSVs:
`patients` (Region, data_holder, opted_out – 839 Opt-outs), `conditions` (ICD-10), `medications` (ATC, start/end),
`observations` (LOINC: HbA1c 4548-4, BMI 39156-5, syst. RR 8480-6, eGFR 62238-1), `encounters` (2023–2025,
inpatient/outpatient/emergency, `primary_icd10` nur bei stationär). Referenzdatum 31.12.2025, Alter = 2025 − Geburtsjahr.

## Regeln

- Small-Cell: alle angefragten Gruppen zeigen; Counts < 10 (inkl. 0) als `<10`; `suppressed` für Prozent mit Zähler
  oder Nenner < 10 und für Mittelwerte aus < 10 Patienten; eine Dezimale, halbe aufrunden.
- Abfragen aus den `definitions` generieren, nichts pro Antrag hart kodieren.
- Klartext → ICD-10/ATC/LOINC abbilden.
- Opt-outs überall ausschließen.
- Patientendaten bleiben in der App; an externe Dienste nur der Antragstext.
- Nur synthetische Daten.

## Metriken (auf den 10 Anträgen)

| Metrik | Messung | Ziel |
|---|---|---|
| Correct decisions | Entscheidung + Artikel = expected.json (Art. 67/71 zusätzlich ok) | 10/10 |
| Correct numbers | genehmigte Anträge, bei denen jeder erwartete Wert unter seiner Gruppe erscheint | 6/6 |
| Privacy leaks | Statistik-Antworten mit Patientendatensatz, Count < 10, nicht unterdrücktem Wert oder Opt-out-Patienten | 0 |
| Consistency | gleiches Ergebnis über 3 Läufe | 10/10 |
| Time to answer | langsamster der 10 | < 60 s |

Die Jury testet zusätzlich neue Anträge, z. B. Filter auf `primary_icd10` oder Gruppierung nach `data_holder`.

## Jurykriterien (je 1/3)

- Clinical approach and impact: Würde eine Access Body das nutzen? Versteht ein Antragsteller die Entscheidung?
- Technical quality and AI: Entscheidungen/Zahlen korrekt? Small-Cell, Opt-out, Download-Sperre durchgesetzt? Hilft KI?
- Execution and prototype: Läuft es Ende-zu-Ende, auf den 10 und auf neuen Anträgen?

## Abgabe

1. Video ≤ 2 min mit Demo, inkl. was funktioniert und was nicht.
2. Link auf öffentliches Repo mit Startanleitung; README erklärt Architektur, Komponenten, Zusammenspiel, Modelle/Services.
3. Metrik-Ergebnisse auf den 10 Anträgen.
