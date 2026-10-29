# Auftrag: Hackathon „Clinical AI – Track 3: European Health Data Space (EHDS)“

Du baust in diesem Repo (OsmanTuerkmen/hackathon-clinical-ai) eine Gewinner-App für Track 3.
Arbeite gründlich, selbstständig und nachvollziehbar. Frag mich nur bei echten Entscheidungen,
die du nicht aus diesem Prompt oder den Aufgabendokumenten ableiten kannst.

Hinweis: Auf dem Branch `worktree-track1-app` liegt Arbeit zu Track 1 (falscher Track). Ignoriere sie, merge sie nicht
und baue nichts darauf auf.

## 0. Arbeitsweise – Superpowers ist Pflicht
Das Plugin „superpowers“ ist installiert. Lade zuerst `superpowers:using-superpowers` und halte dich daran:
Vor jedem Arbeitsschritt prüfst du, welcher Skill passt, und lädst ihn. Verbindliche Abfolge:
1. `superpowers:brainstorming`: Design klären. Spec nach docs/superpowers/specs/.
   Die Anforderungen in Abschnitt 2 sind entschieden und werden nicht neu verhandelt.
   Offen und von dir zu entscheiden sind Stack, Architektur, Datenhaltung und UI-Konzept.
2. `superpowers:using-git-worktrees`: isolierter Branch für die Umsetzung.
3. `superpowers:writing-plans`: Implementierungsplan mit kleinen, testbaren Tasks nach docs/superpowers/plans/.
4. `superpowers:subagent-driven-development` (+ `superpowers:dispatching-parallel-agents` für unabhängige Tasks).
   Jeder Task läuft mit `superpowers:test-driven-development`.
5. Bei jedem Fehler oder jeder falschen Eval-Zahl: `superpowers:systematic-debugging`.
6. Nach jedem Meilenstein: `superpowers:requesting-code-review`. Feedback mit `superpowers:receiving-code-review` prüfen.
7. Bevor du irgendetwas als fertig meldest: `superpowers:verification-before-completion`. Die Eval-Ausgabe ist der Beweis.
8. Zum Abschluss: `superpowers:finishing-a-development-branch`.
Weitere Skills: `claude-api` (falls du Claude nutzt; vor jedem Modell- oder SDK-Code lesen), `security-review`
vor jedem Push, `run` zum Starten und Ansehen der App.

## 1. Setup
- Die Aufgabendaten liegen bereits geklont NEBEN dem Repo: `../track3`
  (README.md, data/*.csv mit 20.000 synthetischen Patienten, data/README.md, requests/R01–R10.json, requests/expected.json).
  Nicht erneut klonen. Tokens NIE in Dateien, URLs oder Commits speichern.
- Lies vollständig: ../track3/README.md, ../track3/data/README.md, alle 10 Requests und expected.json.
- Lies das Gesetz: Verordnung (EU) 2025/327 (EHDS), Kapitel IV, https://eur-lex.europa.eu/eli/reg/2025/327/oj/eng.
  Mindestens Art. 53, 54, 66, 67, 68, 69, 71 und 73. Fasse die für Entscheidungen relevanten Kernaussagen in eigenen Worten in
  docs/LAW.md zusammen (mit Artikelnummern), damit die Begründungen korrekt zitieren.
- Datenpfad konfigurierbar (z. B. ENV TRACK3_DATA, Default ../track3). Die CSVs nicht ins Repo kopieren;
  `.env`, Secrets und erzeugte SPE-Ordner/Datenbanken in .gitignore.

## 2. Anforderungen (fest)
Eine App nimmt einen Antrag als JSON (Format wie requests/R*.json) und macht automatisch:
1. **Entscheidung** `REJECT`, `APPROVE_STATISTICAL` oder `APPROVE_SPE` mit zitierten Artikeln, strikt in dieser Reihenfolge:
   1. Verbotener Zweck (Art. 54): `REJECT`, Art. 54. Beispiele: Versicherungsprämien, Werbung/Marketing,
      Entscheidungen über Beschäftigte, Entwicklung schädlicher Produkte wie Nikotin.
   2. „health data request“: `APPROVE_STATISTICAL`, Art. 53 + 69.
   3. „health data access application“, die begründet, warum Statistik nicht reicht (wie R05): `APPROVE_SPE`, Art. 53, 66, 68, 73.
   4. Jeder andere Access-Antrag (wie R09): `APPROVE_STATISTICAL`, Art. 53, 66, 69.
   Art. 67 oder 71 zusätzlich zu nennen ist ok. Die Entscheidung muss reproduzierbar sein (3 Läufe → identisches Ergebnis).
2. **Statistik:** Zahlen aus den Daten berechnen, mit Small-Cell-Regel:
   - Jede angefragte Gruppe zeigen, auch leere.
   - Counts < 10 (inkl. 0) als `<10`.
   - `suppressed` für Prozentwerte mit Zähler oder Nenner < 10 und für Mittelwerte aus < 10 Patienten.
   - Auf eine Dezimale runden, halbe aufrunden (ROUND_HALF_UP, nicht Bankers' Rounding!).
3. **SPE:** Die Datensätze der ausgewählten Patienten in eine Secure Processing Environment kopieren
   (separates Schema oder Ordner). Nur die ausgewählten Patienten und nur die genannten Record-Typen kopieren,
   Patienten-IDs behalten. Die exakte Patientenzahl berichten (nicht unterdrückt). Downloads blockieren
   und den blockierten Download in der Demo zeigen.
4. **Anzeige:** Entscheidung und Begründung verständlich für den Antragsteller UND für das Personal der Access Body
   (Staff-Ansicht mit Details: erkannter Zweck, angewandte Regel, generierte Abfrage, Code-Mapping, Opt-out-Ausschlüsse).
Weitere feste Regeln:
- **Keine Handarbeit pro Antrag:** Abfragen werden aus den `definitions` des Antrags generiert. Nichts ist pro Request
  hart kodiert. Die Jury testet neue Anträge, z. B. Filter auf Hauptdiagnose stationärer Aufenthalte (`primary_icd10`)
  oder Gruppierung nach Krankenhaus (`data_holder`). Das muss funktionieren.
- **Terminologie-Mapping:** Definitionen nennen Diagnosen, Medikamente und Messwerte in Klartext, die Daten codieren
  sie als ICD-10, ATC und LOINC. Die App muss Klartext auf Codes abbilden, auch wenn ein neuer Antrag keinen Code nennt.
  Sie prüft das Mapping gegen die tatsächlich vorkommenden Codes und zeigt es in der Staff-Ansicht.
- **Opt-out:** Opted-out-Patienten überall ausschließen (Zähler, Nenner, Mittelwerte, SPE).
- **Datenschutz:** Patientendaten bleiben in der App. An externe Dienste (z. B. Cloud-LLM) darf nur der Antragstext,
  niemals Patientenzeilen oder Ergebnisse auf Patientenebene. Statistik-Antworten enthalten nie Datensätze auf
  Patientenebene, nie Counts < 10 und nie unterdrückungspflichtige Werte.
- **Referenzdatum** ist der 31.12.2025. Alter = 2025 − Geburtsjahr. Ein Medikament ist aktiv, wenn
  start_date ≤ Stichtag und end_date leer oder ≥ Stichtag ist.
- **Antwortzeit** < 60 s pro Antrag.
- Klare, vertrauenswürdige UI: Juryfrage „Würde eine Access Body das nutzen? Versteht ein Antragsteller die Entscheidung?“

## 3. Technik – deine Entscheidung
Wähle Sprache, Frameworks, Datenbank/Query-Engine, Modelle und Architektur so, wie es für diese Lösung am besten ist
(Korrektheit, Reproduzierbarkeit, Datenschutz, Geschwindigkeit, Demo-Qualität, Hackathon-Tempo).
Regeln, LLM oder beides; zentrale DB oder föderiert pro Krankenhaus; OMOP/FHIR optional.
Stelle im Brainstorming 2–3 Optionen gegenüber, entscheide begründet und halte das als ADR fest.
Bewährtes Muster, das du prüfen solltest: LLM übersetzt nur den Antragstext in eine strikt validierte, strukturierte
Abfrage-Spezifikation (Zweck-Klassifikation, Kohorte, Gruppen, Kennzahlen, Codes), danach rechnet eine deterministische
Engine (z. B. SQL/DuckDB). Die Small-Cell-Regel wird zentral nach der Berechnung und vor jeder Ausgabe erzwungen.
Für Konsistenz: Temperatur 0, kanonisierte Spec, Caching, deterministische Regeln für die Entscheidungsreihenfolge.

## 4. Evaluation – bauen, laufen lassen, iterieren
- Ein Eval-Skript schickt alle 10 Requests durch die App und misst:
  - **Correct decisions:** Entscheidung und Artikel gleich expected.json; Art. 67/71 zusätzlich ist ok. Ziel 10/10.
  - **Correct numbers:** Jeder erwartete Wert erscheint unter seiner Gruppe. Ziel 6/6 genehmigte Anträge.
  - **Privacy leaks:** Statistik mit Patientendaten, Count < 10, nicht unterdrücktem Wert oder Opt-out-Patienten. Ziel 0.
  - **Consistency:** gleiches Ergebnis über 3 Läufe. Ziel 10/10.
  - **Time to answer:** langsamster der 10. Ziel < 60 s.
- Ergebnisse als Tabelle nach eval/results.md. Iteriere, bis alle Ziele erreicht sind.
- Unabhängige Kontrolle: Rechne die erwarteten Zahlen für R01, R03, R07, R08, R09 und R05 (Kohortengröße) zusätzlich
  mit einem separaten, einfachen Referenzskript nach.
- Schreibe mindestens 8 eigene neue Anträge, darunter:
  - Filter auf `primary_icd10`;
  - Gruppierung nach `data_holder`;
  - Klartext-Definitionen ohne Codes;
  - ein Grenzfall-Verbot;
  - ein SPE-Antrag mit anderen Record-Typen (z. B. Encounters);
  - ein Antrag mit vielen kleinen Zellen.
  Teste die App damit. Legal- und Datenschutz-Logik gehören in Unit-Tests.
- Fallen beachten:
  - R09 ist ein Access-Antrag ohne Begründung, warum Statistik nicht reicht. Ergebnis: APPROVE_STATISTICAL mit Art. 53, 66, 69.
  - R06 (HR/Beschäftigte), R10 (Nikotinprodukte), R02 (Versicherung) und R04 (Werbung) sind alle REJECT nach Art. 54.
  - Bei R07 werden Aufenthalte gezählt, nicht Patienten.
  - Bei R02/R08 gilt der jeweils letzte Messwert pro Patient.
  - Rundung ist halbe aufwärts.

## 5. Dokumentation – laufend pflegen (Pflicht)
Lege gleich zu Beginn an und aktualisiere nach JEDEM abgeschlossenen Task bzw. Meilenstein:
- `CLAUDE.md`: Projektüberblick, Befehle (Setup, Start, Test, Eval), Architektur kurz, Konventionen, harte Regeln
  (keine Patientendaten an externe Dienste, Small-Cell-Regel, Opt-out, keine Secrets, Superpowers-Workflow),
  Verweise auf docs/.
- `AGENTS.md`: gleicher Inhalt für andere Agenten; nicht doppelt pflegen (eine Datei verweist auf die andere).
- `docs/CHALLENGE.md`: Aufgabe, Regeln, Metriken, Jurykriterien, Abgabe.
- `docs/LAW.md`: relevante EHDS-Artikel in eigenen Worten und die Entscheidungslogik.
- `docs/GOALS.md`: Ziele und Erfolgskriterien.
- `docs/STATUS.md`: aktueller Stand, was funktioniert, was nicht, letzte Metrikwerte, Datum.
- `docs/TODO.md`: offene Aufgaben, priorisiert.
- `docs/DECISIONS.md` (oder docs/adr/): Entscheidungen mit Kontext, Optionen, Begründung.
- `docs/WORKLOG.md`: chronologisches Log.
- `docs/superpowers/specs/` und `docs/superpowers/plans/`: von den Skills erzeugt.
- `README.md` (Abgabe): Ziel, Screenshot/GIF, Setup und Start, Architektur mit Komponenten, Datenfluss, Modellen und
  Services (Mermaid), Datenschutzkonzept, Metrik-Tabelle, bekannte Grenzen.

## 6. Git
- Kleine, sinnvolle Commits. Vor jedem Commit `git status` prüfen: keine CSV-Daten, keine SPE-Kopien, keine .env.
- `security-review` vor dem ersten Push und vor der Abgabe.
- Push erst nach meiner Freigabe. Das Repo bleibt privat, bis ich es für die Abgabe öffentlich mache.

## 7. Abschluss
Melde erst „fertig“, wenn `superpowers:verification-before-completion` erfüllt ist. Dann:
- Metrik-Tabelle mit echten Eval-Ergebnissen;
- was funktioniert und was nicht;
- wie man die Demo startet, inkl. blockiertem SPE-Download;
- Vorschlag für das 2-Minuten-Video-Skript;
- aktualisierte docs/STATUS.md und docs/TODO.md.
