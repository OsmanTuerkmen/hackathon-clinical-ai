# Verbesserungsvorschläge für `track3-app`

Grundlage: Kaans Prototyp im Branch `feature/track3-ehds-access-desk`, Ordner `track3-ehds/`. Ansehen ohne Wechsel:
`git show feature/track3-ehds-access-desk:track3-ehds/desk/<datei>.py`.

Dort gemessen (R01–R10, je 3 Läufe):
- 10/10 Entscheidungen mit den richtigen Artikeln
- 6/6 Zahlen
- 0 Privacy-Leaks
- 10/10 konsistent
- langsamste Antwort etwa 0,22 s

Dazu 97 Unit-Tests und 28 Browser-Checks.

Die Vorschläge sind nach Nutzen für die Bewertung sortiert. Jeder Punkt sagt, **was**, **warum**, **wo es in Kaans
Branch steht** und **wie man es prüft**. Bitte jeden Punkt erst prüfen (Brainstorming/Spec), nicht blind
übernehmen. Die Architektur von `track3-app` ist führend.

## Hoch (direkt bewertungsrelevant)

1. **Verneinungslücke bei Art. 54 schließen** (bekannte Grenze in `docs/TODO.md`, ADR-007, R11).
   - **Was:** „No, we will use the data for advertising.“ und Einschübe mit „not …, but …“ rutschen durch. Bei
     Kaan sind die Regeln dreistufig:
     - verbotene Muster führen zu `REJECT`;
     - harmlose Gegenbeispiele werden ausgenommen, z. B. eine Kampagne *gegen* Glücksspielsucht, Arbeitsmarktforschung,
       Preispolitik für Arzneimittel, die Rekrutierung von Studienteilnehmern;
     - Warnsignale ohne eindeutigen Verbotstreffer (Kundenansprache, Preise, Versicherung, Personalentscheidungen,
       einzelne Personen) werden **nie automatisch genehmigt**, sondern gehen an Staff.
   - **Wo:** `desk/policy.py`, Tests `tests/test_policy.py`, mit 24 verbotenen und harmlosen sowie 6 verschleierten
     Formulierungen.
   - **Prüfen:** die Sätze aus R11 und die Testsätze aus Kaans `test_policy.py` gegen `decision.py` laufen lassen.
2. **Eval-Harness mit den 5 Metriken** (Task 13 ist offen).
   - **Was:**
     - Jeder Antrag läuft 3-mal, jedes Mal mit frischem Laden der Daten.
     - Erst danach wird mit `expected.json` verglichen, die Datei wird also nie zur Antwort benutzt.
     - Gemessen werden Entscheidung plus Artikel, Zahlen, Leaks, Konsistenz und Maximalzeit.
     - Es gibt einen Modus über HTTP (`--url`) und einen Tab „Evaluation“ in der UI.
     - Ein statischer Test sichert ab, dass kein Laufzeitcode `expected.json` liest.
   - **Wo:** `desk/evaluate.py`, `tests/test_supplied_requests.py`.
3. **Unabhängiges Privacy-Audit nach der Disclosure.**
   - **Was:** Eine eigene Stufe prüft jede freigegebene Zelle erneut gegen die Rohwerte, mit diesen Regeln:
     - `<10` gilt auch für 0;
     - Prozent mit Zähler oder Nenner unter 10 wird unterdrückt;
     - Mittelwerte bei Encounter-Daten zählen *verschiedene Patienten*;
     - es gibt keine IDs und keine Einzeldatensätze.
   - Bei einem Fehler gibt die Pipeline nichts frei (fail closed). Die Anzahl der Checks speist den Privacy-Ring im
     Dashboard („7/7 checks passed“).
   - **Wo:** `desk/audit.py`, `desk/disclosure.py`.
4. **Kurzbegründung, „You receive“-Zeile und Bescheid-PDF.**
   - **Was:**
     - Pro Outcome gibt es einen Satz in einfacher Sprache, z. B. „Not allowed: … (Art. 54(1)(d)).“
     - Eine Zeile sagt, was der Antragsteller erhält.
     - Die ausführliche Begründung ist aufklappbar.
     - `GET /api/cases/<id>/letter.pdf` liefert den vollständigen Bescheid. Er wird mit einem kleinen PDF-Writer
       nur aus der Standardbibliothek erzeugt (Helvetica, Zeilenumbruch, Seitenumbruch) und enthält keine
       Patientenkennungen.
   - **Wo:** `desk/pipeline.py` (`short_reason`, `receive_text`), `desk/letter.py`, Test
     `tests/test_server.py::test_short_reason_and_pdf_decision_letter`.
5. **Toleranter Import für Jury-Uploads.**
   - **Was:** Gängige Abweichungen werden normalisiert statt abgelehnt, und es wird vermerkt, was angepasst wurde:
     - Byte-Order-Mark am Dateianfang;
     - eine Liste von Anträgen oder ein verpackter Antrag;
     - andere Feldnamen (`Type`, `Format`, `Purpose`);
     - Definitionen als ein Textblock;
     - fehlende Antragsart oder fehlendes Format.
   - Unverständliches wird weiterhin abgelehnt.
   - **Wo:** `desk/request_schema.py` (`_lenient`), `tests/test_request_schema.py`.

## Mittel (Robustheit und Bedienbarkeit)

6. **Alle Gruppierungen kombinierbar.**
   - **Was:** Bei Kaan scheiterte ein Report mit Region, Altersgruppe, Geschlecht und Spital an einem Limit von 3
     Dimensionen. Bitte prüfen, ob `track3-app` alle 4 `Dimension`-Arten gleichzeitig erlaubt.
   - Als Obergrenze reicht die Gesamtzahl der Gruppen, bei Kaan 2000.
7. **Abgeleitete Werte.**
   - **Was:**
     - Alter ist 2025 minus Geburtsjahr.
     - Die Liegedauer ist `end_date − start_date`, wahlweise inklusive mit `+1`. Für den Mittelwert unter 10 zählen
       verschiedene Patienten, nicht Aufenthalte.
     - Minimum und Maximum werden abgelehnt, weil sie Einzelpersonen beschreiben können.
   - **Wo:** `desk/parser.py`, `desk/executor.py`, `new_requests/N07.json` und `N08.json`.
8. **SPE datensparsam und nutzbar.**
   - **Was:**
     - Es werden nur die angefragten Messwerte kopiert, z. B. bei „HbA1c measurements“ nur LOINC 4548-4.
     - Pro Genehmigung gibt es einen Token. Nur gespeichert wird sein Hash.
     - Innerhalb der SPE sind aggregierte Auswertungen erlaubt, mit Small-Cell-Prüfung vor dem Export.
     - Jeder Download-Versuch bekommt HTTP 403 und wird protokolliert.
   - **Wo:** `desk/spe.py`.
9. **Geführter Assistent statt Freitext-Definitionen.**
   - **Was:** Man wählt Gruppe (Alter, Geschlecht), optional Diagnose, Medikament oder Messwert und die Gruppierung.
     Der Assistent schreibt daraus die Definitionszeilen im Challenge-Format, mit Codes aus dem Lexikon.
     „Write it myself“ bleibt für Sonderfälle.
   - Das senkt Parser-Fehler bei Nicht-Technikern stark.
   - **Wo:** `web/app.js` (`assistantLines`), `GET /api/vocabulary` (`desk/vocabulary.py::catalog`).
   - **Hinweis:** Die Begriffe dürfen kein „and“, „or“ oder Komma enthalten, weil sie sonst die Report-Zeile spalten.
10. **Simulierter ID-Austria-Login, nur für Antragsteller.**
    - **Was:**
      - Ablauf wie beim echten Dienst (OIDC Authorization Code Flow) gegen einen Mock-IdP mit fiktiven Testpersonen.
      - Schutz: `state`-Prüfung, Einmal-Codes, keine offenen Redirects.
      - Der Fall speichert nur Name, eIDAS-Stufe und ein bPK-artiges Pseudonym. Die Entscheidung nutzt die Identität
        nie.
    - **Wo:** `desk/identity.py`, `web/idp.html`, `web/idp.js`.
    - Echte Anbindung: Registrierung im IDA-SPR, `client_secret`, `idp.ref.id-austria.gv.at`.

## Niedrig (Qualität und Demo)

11. **HTTP-Härtung:**
    - Größenlimit des Request-Bodys (413);
    - ungültiges UTF-8 oder ein ungültiger `Content-Length` führt zu 400;
    - interne Fehler liefern 500 ohne Daten;
    - Security-Header und CSP.

    Ein Test schickt 24 gleichzeitige Anträge mit identischem Ergebnis. **Wo:** `desk/server.py`,
    `tests/test_server.py`.
12. **Browser-E2E ohne npm** über das Chrome DevTools Protocol. Geprüft werden:
    - die Demo-Fälle;
    - XSS wird als Text angezeigt;
    - Upload und ungültiges JSON;
    - Handy-Breite ohne horizontales Scrollen;
    - keine Konsolen- oder CSP-Fehler.

    **Wo:** `tests/e2e/browser_flow.mjs`.
13. **CSV nur für anonymisierte Tabellen**, klar beschriftet als `Download anonymised statistics (CSV)`. In der SPE
    ist der Download von Datensätzen immer blockiert.
14. **Persistentes Fallregister** (`state/cases.jsonl`, ohne Patientendaten), damit die Staff-Ansicht einen Neustart
    übersteht.
15. **Einblend-Animation, nur einmal** beim Öffnen und abgeschaltet bei `prefers-reduced-motion`. Optional:
    `tools/record_demo.mjs` nimmt eine stumme Demo als MP4 auf (nur macOS/Chrome).

## Bewusst nicht übernehmen

- Kaans stdlib-HTTP-Server: `track3-app` nutzt FastAPI, das bleibt so.
- Kaans Regex-Parser 1:1: `track3-app` hat einen eigenen, gut getesteten Regelparser (211 Probes, 0 „vollständig,
  aber falsch“). Nur die Testfälle und Formulierungen aus Kaans `tests/test_paraphrases.py` als zusätzliche Probes
  verwenden.
