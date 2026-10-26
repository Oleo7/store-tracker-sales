# Store Tracker Sales

Kodbas för ett säljorienterat CRM med Flask, Google Sheets, kundprioritering,
kontaktlogg, kalender, ruttplanering och säljuppföljning.

**Det här är ett separat repository från originalet `Oleo7/store-tracker`.**
Ändringar i det här repot får inte användas för att uppdatera originalets kod
eller originaldatabasen `CRM_DATABASE`.

## Syfte med denna version

Det här repot förbereds för överlämning till en utvecklarkollega. Det är **inte
ännu ett företagsoberoende eller multitenant CRM**: flera aktiva regler,
inställningar och integrationer är Polarbär-specifika.

PR1 tog bort automatiska mejlförslag/Brevo. PR2 tog bort verifierat död kod.
Den påföljande överlämningsrensningen tar bort ytterligare oanvända hjälpare och
inaktiva workflow-adaptrar utan att migrera befintlig data.

**Ingen ny Render-miljö, ny Google Sheet eller driftsättning krävs för att granska
och vidareutveckla repositoryt.** Det befintliga `render.yaml` är kvar som
referens men ska inte användas för att oavsiktligt skapa eller ändra en tjänst.

**Börja här:** [Teknisk överlämning och kvarvarande legacy](docs/HANDOVER.md).

## Aktiv kod

| Del | Primära filer |
| --- | --- |
| Flask, autentisering, kund-/kontakt-/kalender-API | `web-app/app.py` |
| Webbläsargränssnitt | `web-app/index.html` |
| Kundprioritering, V3.5 | `web-app/priority.py`, `web-app/value_prioritization.py` |
| Kund- och uppföljningstillstånd | `web-app/customer_obligations.py` |
| Förslag och händelseloggar | `web-app/planning_suggestions.py`, `web-app/sales_coaching.py` |
| Rutter | `web-app/route_proposal.py`, `web-app/route_optimization.py` |
| Order och kundmaster | `stockfiller_orders/sync.py`, `customer_master_sync/sync.py` |
| Integrationer som fortfarande finns kvar | `web-app/instagram_feed.py`, `web-app/meta_ads.py`, `storepoint_sync/sync.py` |

Se [överlämningsguiden](docs/HANDOVER.md) innan du raderar äldre fält,
API:er, ruttfunktioner eller databasblad. Vissa är fortfarande aktiva även om
deras namn innehåller `legacy`.

## Kontrollera koden utan Render eller produktionsdata

GitHub Actions kör en syntetisk testsuite för pull requests via
`.github/workflows/sales-coaching.yml`. Testerna använder isolerade fixtures
och behöver ingen ny Render-tjänst.

Rekommenderad lokal kontroll, från repositoryts rot:

```bash
python -m pip install -r requirements-test.txt
python -m unittest discover -s web-app/tests -p 'test_*.py'
python -m unittest discover -s tests -p 'test_*.py'
```

GitHub Actions kör dessutom frontendkontrakt och Chromium-smoketester.
För enbart källkodsgranskning behövs inga kunduppgifter eller Google-nycklar.

## Om någon senare vill köra applikationen

Studera `.env.example` och de aktiva skriv-/behörighetsspärrarna först.
Använd **aldrig** originalets databas eller tjänster som testmiljö. Hantera
`GOOGLE_CREDENTIALS`, API-nycklar och sessionshemligheter som hemligheter.
Skicka inte credentials till repositoryt, issues eller PR-kommentarer.

Befintlig driftkonfiguration finns i `render.yaml`, men att kopiera eller
aktivera den ingår **inte** i denna överlämning. Konfigurationen innehåller
fortfarande Polarbär-specifika värden.

## Dokumentation

- [Överlämning och kvarvarande legacy](docs/HANDOVER.md) — **läs först**.
- [Borttagning av automatiska mejl](docs/email-integration-removal.md).
- [Aktuell prioriteringsmodell V3.5](docs/value-contact-priority-v35.md).
- [Kundaktivitet och säker planering](docs/customer-activity-loop.md).
- [Synkronisering av kundmaster](docs/customer-master-sync.md).

Äldre QA-rapporter, tidigare modellversioner och historiska releaseinstruktioner
finns kvar för spårbarhet. De ska inte betraktas som uppdaterade
installations-/driftsinstruktioner.
