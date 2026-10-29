# Ziele und Erfolgskriterien

## Muss (Abnahme)

| Ziel | Kriterium | Nachweis |
|---|---|---|
| Korrekte Entscheidungen | 10/10 inkl. Artikel | `eval/results.md` |
| Korrekte Zahlen | 6/6 genehmigte Anträge, unabhängig nachgerechnet | `eval/results.md`, `eval/reference.py` |
| Keine Datenschutzlecks | 0 Leaks; Leak-Guard vor jeder Ausgabe | Eval + Unit-Tests `disclosure` |
| Konsistenz | 10/10 identisch über 3 Läufe | Eval |
| Antwortzeit | langsamster Antrag < 60 s | Eval |
| Neue Anträge | ≥ 8 eigene Anträge (primary_icd10, data_holder, Klartext, Grenzfall-Verbot, SPE mit Encounters, viele kleine Zellen) korrekt | Eval über `requests/extra/` |
| SPE | nur Kohorte, nur genannte Record-Typen, IDs erhalten, kein Opt-out, Download blockiert + protokolliert | Unit-Tests `spe`, Demo |
| Nachvollziehbarkeit | Staff-Ansicht zeigt Zweck, Regel, Spec, SQL, Code-Mapping, Opt-out-Ausschlüsse | Demo |

## Soll (Jury-Wirkung)

- Antragsteller versteht die Entscheidung ohne Jurawissen (Klartext + Artikel-Chips mit Kurzfassung).
- Staff kann jede Zahl bis zum SQL zurückverfolgen.
- App läuft ohne API-Key vollständig; mit Key verbessert ein LLM die Robustheit gegenüber neuen Formulierungen.
- README mit Architekturdiagramm, Datenschutzkonzept, Metriktabelle und ehrlichen Grenzen.

## Kann

- Sekundäre Unterdrückung, föderierte Ausführung pro Klinikum, OMOP/FHIR – bewusst nicht im Umfang.
