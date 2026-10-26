# Överlämning: Store Tracker Sales

## 1. Mål och status

Detta är den fristående kodbasen `Oleo7/store-tracker-sales`, framtagen ur
Polarbärs Store Tracker. Syftet i denna fas är att **städa och dokumentera
koden för en kollega**, inte att migrera historik eller lansera en ny tjänst.

**Inte gjort i överlämningsrensningen:** ny Render-tjänst, driftsättning,
uppdatering av någon Google Sheet, ändring av originalrepon
`Oleo7/store-tracker` eller originalets `CRM_DATABASE`, generell
företagskonfiguration eller multitenant-arkitektur.

**Viktigt:** GitHub-repot har historik från Polarbär. En ren kodbas betyder
inte att aktiva affärsregler automatiskt är företagsneutrala.

## 2. Läsordning och verifiering

1. Läs `README.md`, denna guide och `docs/email-integration-removal.md`.
2. Läs `docs/value-contact-priority-v35.md` för aktiv scoring och
   `docs/customer-activity-loop.md` för dagens uppföljningssemantik.
3. Granska aktuellt `master` och GitHub Actions på den PR som ska användas.
4. Kör befintliga Python-, frontend- och browser-regressioner mot syntetisk data.
5. Testa senare mot en separat, uttryckligen vald miljö **först när det behövs**.

Testsuiten i `.github/workflows/sales-coaching.yml` kör Pythonkompilering,
web-appens och rotens enhetstester, frontendkontrakt, desktop/mobil och
smoketester för prioritering, kalender, rutter och tidigare mejl-integration.

Detta räcker för en **källkods- och regressionsöverlämning**. Det är inte samma
sak som en verifierad ny kundinstallation eller produktionsdriftsättning.

## 3. Arkitektur och aktiva flöden

| Flöde | Nuvarande ansvar |
| --- | --- |
| Kundregister | `customers_enriched` med stabilt `customer_id` |
| Orderhistorik | `order_rows`, i dagsläget Stockfiller-format |
| Kontakter | `sales_activities`, mänskliga kontakter och förhandsberäknade snapshots |
| Kalender | `planned_activities`; ansvar, status och idempotenta mutationer |
| Rekommendationer | `planning_suggestions`, `score_events`, aktuella V3.5-kandidater |
| Kund-/uppföljningsprojektion | `customer_state_events` och aktiva kalender-/kontaktkällor |
| Rutter | `route_proposals` och `route_optimization_runs` |
| Inloggning/parametrar | `users` och `settings` |
| Ordersynk | `_stockfiller_sync_state`, ev. `_customer_sync_review` |

De nämnda bladen är **inte en raderingslista**. Vissa innehåller aktiv state,
andra historiska spår som dagens kod fortfarande avgränsar. Ingen rad eller
kolumn har migrerats eller raderats i denna överlämning.

De viktigaste filerna finns samlade i rot-README. `web-app/app.py` och
`web-app/index.html` är stora filer; senare moduluppdelning bör göras i egna
testade PR:er, inte under historikradering.

## 4. Legacy som avsiktligt är kvar

| Kod/kontrakt | Varför det är kvar | Vad som krävs före borttagning |
| --- | --- | --- |
| `email_id`, `crm_email` och filtren `is_human_contact` / `is_retired_email_tracking_snapshot` | Hindrar gamla automatiska mejl och klick från att räknas som säljararbete eller ge fel poäng | Separat datarensning och regressionsbevis på både kontakter och historiska rekommendationer |
| `active_email_intent_event` i gammalt context-hash | Tom kompatibilitetspost som bevarar äldre rekommendations-ID:n | Versionsbyte av ID-format och kontroll av kopplade aktiviteter |
| Kontaktradens `follow_up_date`, virtuella uppföljningar och `/customer-obligations/action` | Äldre datumuppföljningar saknar egen kalenderpost men kan fortfarande hanteras | Inventera/revidera äldre rader och ersätt adapter med kalenderkontrakt |
| Rekonstruktion av historiska scoring-snapshots i `sales_coaching.py` | Gamla kontakter saknar exakt loggad V3.5-snapshot | Definiera ny analyssemantik och migrera eller acceptera saknade historiska snapshots |
| Kundnamnsbaserade insights-svar och versionsheaders | Bakåtkompatibilitet med äldre klientformat | En kontrollerad API-versionsändring och uppdaterade frontend-/replaytester |
| `legacy_missed_followup` och äldre triggeralias | Historiska planeringsposter och deras relationer | Utred att inga aktiva beslut längre beror på aliasen |
| `/route-proposal` och `/planning/route-import` | Den gamla frontendens panel och importanrop tas bort i PR4. Backend-API:erna finns ännu kvar som kompatibilitet för eventuella externa klienter; kalenderns aktiva ruttflöde använder andra API:er. | Bevisa att ingen extern klient använder API:erna innan separat backendrensning |
| `ROUTE_ENGINE=legacy` | **Aktivt namn på lokal ruttmotor**, inte automatiskt död kod | Kräver separat beslut om ruttmotor, inte historikrensning |
| `route_proposal.py` och `route_proposals` | Delar av logiken/lagringen används av aktuell ruttberäkning, återförsök och idempotens | Granska på funktionsnivå innan någon modul/worksheet tas bort |
| Avvecklade API-endpoints som returnerar HTTP 410 | Spärrar gamla klienter från att utföra pensionerade mutationer | Beslut att gamla API-kontrakt får försvinna; kontrollera beroende klienter |
| Engångsmigrerings- och recovery-skript under `scripts/` | Används inte av ordinarie webbruntime, men kan fortfarande behövas för manuell diagnos/reparation | Dokumentera vilka historiska scenarier som definitivt är avslutade |

**Ta inte bort säkerhetsspärrar** för `customer_id`, revisionsnummer,
`client_request_id`, lås, rollkontroll eller ruttens källverifiering bara
för att deras kod nämner gammal historik.

`web-app/tests/historical_priority_reference.py` är en frusen **testreferens**,
inte en aktiv V2-motor. Den skyddar mot oavsiktlig återgång till gamla
scoringregler och har medvetet sparats.

## 5. Aktiv Polarbär-kod — inte samma sak som död legacy

Det finns fortfarande aktiva specialregler som är ett eget framtida
generaliseringsprojekt:

- `web-app/priority.py` filtrerar vissa Polarbär-benämnda interna order.
- `customer_master_sync/sync.py` innehåller specifika undantag för interna kunder.
- `web-app/app.py` och frontend lagrar observationer om Polarbär och
  namngivna konkurrenter i frysdisken.
- `web-app/value_prioritization.py` har DFP-baserade kommersiella antaganden,
  segmentpriorer och kontaktregler.
- Stockfiller, Instagram, Meta Ads och Storepoint är fortfarande
  leverantörs-/verksamhetsspecifika integrationer.
- `render.yaml` och `.env.example` har ännu Polarbär-relaterad konfiguration.

Det är inte säkert att radera ovanstående som ”legacy” utan ett produktbeslut.
Nästa utvecklare bör först välja vilka funktioner en framtida CRM-produkt
faktiskt ska ha, och därefter göra konfiguration eller modulborttagning.

## 6. Genomförda rensningar

- **PR1:** automatiska mejlförslag, Brevo, utskicksspårning och därav beroende
  mejluppföljning borttagen. Manuella mejlkontakter kvar.
- **PR2:** verifierat oanvända hjälpfunktioner och ett no-op
  `superseded`-reconciliation-skript borttagna.
- **PR3 (överlämningsrensningen):** oanvända frontend-/backendhjälpare och
  no-op workflow-suppression borttagna; regressionstester och replayverktyg
  anpassade; README och denna överlämningsguide förtydligade.
- **PR4 (ruttgränssnitt):** den gamla, oåtkomliga ruttförslagspanelen och dess
  JavaScript/CSS, API-anrop och specialfall i kundlista/karta avvecklas.
  Manuell Google Maps-rutt, sparat kartutkast, kalenderns ruttförhandsgranskning,
  GPS, restidsvisning, fallback, ruttsparning, gemensam ruttmotor och
  `route_proposals`-bladet bevaras. Äldre backend-API:er avvecklas **inte**.

Alla framtida ändringar görs i `Oleo7/store-tracker-sales` och helst en separat
PR per riskområde. **Ingen automatisk merge eller deployment följer av denna
guide.**

## 7. Förslag på fortsatt arbete för kollegan

1. Starta med kodgranskning och en fristående historik-/API-inventering. Märk
   beroenden som `ACTIVE`, `HISTORICAL_REQUIRED`, `TEST_ONLY` eller `UNUSED`.
2. Förenkla gamla API-/datakontrakt en kategori i taget, med regressioner för
   befintlig kopia och en separat, explicit migrationsplan om data behöver ändras.
3. **PR5 – kalendern äger uppföljningar.** Den nya koden i `store-tracker-sales`
   ignorerar `sales_activities.follow_up_date`, skriver och speglar inte kolumnen,
   och skapar inte virtuella uppföljningar av gamla kontaktloggar. Planerade
   aktiviteter med stabila ID:n är den enda operativa källan. Den gamla
   datakolumnen i befintlig kopia kan ligga kvar som historiskt rådata tills
   en separat, verifierad databasmigrering har godkänts; kodmodellen kräver
   inte kolumnen. Originalets Store Tracker påverkas inte.

   **PR5:s operativa kontrakt och säkerhetsgränser:**
   - En uppföljning är en faktisk rad i `planned_activities` med ett
     `planned_activity_id`. Missade aktiviteter, ombokning och Hoppa över
     använder samma kalenderobjekt. `/customer-obligations/action` returnerar
     HTTP 410 och skapar inga nya kalender- eller händelserader.
   - `source_contact_id` kan kopplas till en ny uppföljning endast om det
     finns exakt en motsvarande kontakt globalt, kunden stämmer och användaren
     har behörighet. Kontroll och kalenderappend sker under skrivlås.
   - En kontakt sparas utan datum-mirror. Om kontakten även begär en
     uppföljning måste kalenderappend lyckas; ett delvis lyckat resultat
     rapporteras för idempotent retry med samma request-ID.
   - Historiska datum i den kopierade `sales_activities.follow_up_date`
     får ligga kvar som rådata men producerar **inte** längre åtgärder.
     Före framtida driftsättning på en redan använd databas måste ägaren
     separat inventera äldre datum utan kalenderaktivitet och besluta om
     eventuella manuella/migrerade uppföljningar. Att mergea PR5 är **inte**
     samma sak som att godkänna datamigrering eller driftsättning.
   - PR5:s regressionsgrind omfattar hela Python-/frontend-testsviten samt
     webbläsartester för dator och mobil, kalenderdrag, prioritering,
     säljarflöden, ruttplanering och missade kalenderaktiviteter.
     Inga produktions-Sheets- eller Render-skrivningar ingår.
4. Ta ställning till produktens omfattning: vilka Polarbär-specifika analyser,
   produktfält och integrationer ska bli valbara eller tas bort?
5. Dela senare `app.py` och `index.html` i mindre moduler **utan att samtidigt**
   ändra affärsregler, ruttalgoritm eller datalagring.
6. Separat inför eventuell driftsättning: välj egen testmiljö, granska
   Google-behörigheter, secrets, datamodell, skrivrutiner och Render-konfiguration.
   Den nuvarande överlämningen behöver inget av detta.

## 8. Säkerhets- och överlämningsgränser

- **Originalrepon och originaldatabasen är utanför arbetets scope.**
- En befintlig databaskopia kan ha historiska rader; utgå inte från att den är tom.
- Repositoryt är publikt vid överlämningen. Lägg inte till personlig data,
  kundregister, credentials, hemliga URL:er eller tokens i kod eller dokument.
- `render.yaml` finns kvar oförändrad; en framtida deploy ska kräva ett tydligt
  beslut. Att arbeta i en PR-branch är inte en funktionsverifierad deploy.
- Korrekt körning av syntetiska tester bevisar inte att varje äldre extern
  integration eller datamigrering är säker att avveckla.

**Definition av klart för denna fas:** en begränsad och granskad kodrensning,
fullt gröna CI-regressioner, tydlig karta över aktiva/historiska beroenden
och ingen ändring i Render, Google Sheets eller originalrepon.
