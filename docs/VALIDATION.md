# Verifiche e stato di pubblicazione

## Stato online confermato dal proprietario

Il 23 ottobre 2026 il proprietario ha fornito schermate del risultato della query
`edge_spx_raw_reader_v1` (ruolo authenticated, solo SELECT) e dell'app autenticata
su [Streamlit Community Cloud](https://spx-edge-gex-lab-djvbrdhckns6fv4exbgxos.streamlit.app/).
La schermata dell'app mostra selezione automatica di una fotografia SPX reale
archiviata, quattro scadenze, 1.739 contratti validi su 1.880 e risultati Edge.
Questo conferma avvio, login, lettura privata e completamento del calcolo nel
browser del proprietario. Nessun file originale, UID o segreto viene pubblicato
come prova nel repository.

Il runner resta privo di accesso alla sessione privata e ai byte di quella
fotografia: il test reale locale non e' stato eseguito. Successivamente il
proprietario ha fornito il CSV del profilo e il rapporto JSON generati dalla
stessa app: il controllo scalare online risulta superato su tutti i 1.739
contratti validi. I rapporti esportati sono stati esaminati nel runner, senza
pubblicarli nel repository. L'aggiornamento con una fotografia successiva non
e' ancora stato osservato online; la sostituzione del file e' coperta dai test
locali simulati.

## Verifiche locali

Verifiche nell'ambiente di sviluppo, 23 ottobre 2026, Python 3.12.14:

| Controllo | Esito |
| --- | --- |
| Installazione runtime e sviluppo | Completata, dipendenze fissate con constraints |
| Ambiente pulito con solo `requirements.txt` | Avvio e calcolo sintetico Streamlit verificati senza FastAPI o pytest |
| `python -m pip check` | Nessuna incompatibilità rilevata |
| Suite originale Edge | 212 test passati |
| Suite completa, inclusi wrapper, Storage e Streamlit | 338 passati, 1 saltato |
| Stessa suite con Python 3.14.9 e PyArrow 24.0.0 | 338 passati, 1 saltato |
| Test reale SPX | Saltato esplicitamente: fotografia assente |
| Verifica scalare indipendente sul nuovo esempio sintetico | 40 contratti, NET e gross riconciliati |
| Streamlit AppTest | Avvio senza Secrets, calcolo sintetico nelle tre modalità, sorgenti non configurate |
| Processo Streamlit locale | Home HTTP 200; health HTTP 200 con risposta `ok` |
| Protocollo WebSocket reale su Python 3.14.9 | Pagina iniziale e cinque metriche sintetiche ricevute, bind predefinito dual-stack |
| Frontend originale, Node.js 24.19.0 | `npm ci` e `npm run build` completati |
| Codice originale `gexlab/` | 25 file Python identici allo ZIP |
| Richieste Supabase reali dal runner | Non eseguite: nessuna credenziale privata nel runner; lettura online confermata dalla schermata del proprietario |
| Streamlit Community Cloud | App funzionante nel browser del proprietario, con fotografia reale e risultati; URL non raggiungibile dal proxy del runner |

I test Storage usano `httpx.MockTransport`, senza scritture remote o test di
privilegi tramite tentativi di modifica. Controllano GET, bucket e host,
credenziali privilegiate note, assenza di redirect, limiti di dimensione ed errori
senza token. Non attestano policy o accessibilità del progetto Supabase reale.

La suite emette avvisi di deprecazione di dipendenze: FastAPI/Starlette sul
client di test e `exchange_calendars`/NumPy sulle unità dei timedelta. I test
terminano con successo; gli avvisi non vengono soppressi.

## Diagnosi del deploy Community Cloud

Il log fornito dal proprietario mostra installazione completata, Python 3.14.9,
sostituzione automatica di PyArrow 26 con 24 per `apache/arrow#50471`, e avvio
Uvicorn sulla porta 8501. Non contiene un traceback che spieghi il caricamento
infinito osservato nel browser. Il repository ora richiede direttamente PyArrow
24.0.0, in modo da allineare le installazioni locali e Cloud senza la sostituzione.

Riprodotti localmente Python 3.14.9, le dipendenze e il bind predefinito `::`:
test e controllo WebSocket completo riescono. Il bind è dual-stack e accetta
IPv4: non è stato identificato come causa del problema. Non sono stati disattivati
controlli CORS, XSRF o TLS.

La connessione a `spx-edge-gex-lab-djvbrdhckns6fv4exbgxos.streamlit.app` dal
runner rimane bloccata dal proxy prima di raggiungere l'app. Il funzionamento
online e' stato successivamente confermato dalle schermate del proprietario;
non e' una verifica HTTP o browser eseguita direttamente dal runner.

## Risultato sintetico riproducibile

Comando:

```bash
.venv/bin/python scripts/verify_snapshot.py fixtures/synthetic_cboe_spx.json
```

- Fotografia **sintetica**, timestamp `2026-10-14 13:59:03 UTC`.
- Spot 6.000; modalità prossime quattro scadenze: 14, 15, 16 e 19 ottobre 2026.
- 40 contratti validi verificati; call wall e put wall: 6.000.
- NET GEX: `727812426.027492 USD/1%`.
- Gross GEX: `4612145474.153291 USD/1%`.
- Copertura GEX stimata: 100%; nessun attraversamento dello zero nella finestra.
- SHA-256: `a6fe9e282a8b914b7e8bfb6356691a7b6c0b0142e1595b975c54f259398b7a4e`.

Questo controllo non sostituisce la verifica con una fotografia reale CBOE.
La formula scalare riusa selezione e tempi del wrapper: non è una verifica
indipendente dell'origine, delle quotazioni o delle convenzioni del mercato.
I test separati verificano tempo residuo, contratti AM già regolati, chiusura,
festività, DST, scadenze e riconciliazione del profilo.

## Verifica aritmetica della fotografia reale

L'archivio automatico ora confronta ogni nuova fotografia/modalita' con la formula
scalare separata di `edge_verification.py`. Il controllo riconcilia il GEX di ogni
contratto valido e i totali NET/Gross prima di mostrare i risultati; se fallisce,
mostra un errore senza metriche o rapporto di successo. Non modifica il motore
originale, i dati o i permessi Supabase.

Il rapporto `Scarica verifica Edge JSON` contiene hash del file, modello,
scadenze, numero di contratti e totali del motore e della formula scalare, senza
credenziali o catena originale. Risultati e rapporto restano nella sessione
privata e vengono eliminati al logout. Un poll con file e modalita' invariati
riusa il controllo precedente; un file diverso o cambio di modalita' lo ripete.

Il confronto riusa selezione e tempi residui del wrapper. Non certifica fonte,
qualita' delle quotazioni, posizioni dealer o convenzioni di regolamento.
Il rapporto JSON reale fornito dal proprietario riporta `arithmetic_check: passed`
e `contracts_cross_checked: 1739`, pari a tutti i contratti validi su 1.880.
NET e Gross coincidono con i rispettivi totali scalari, con differenza zero nei
valori esportati. Il runner ha controllato questi confronti e la coerenza dei
metadati, inclusa la regola di valutazione all'ultima chiusura fuori sessione.

Il CSV associato contiene 239 strike nella fascia del grafico: valori finiti,
strike unici e ordinati, OI intero non negativo, segni call/put e riconciliazione
NET = Call + Put su tutte le righe. Call wall e put wall coincidono con il JSON.
La differenza rispetto ai totali della catena e' compatibile con i contratti
esterni alla fascia CSV: il gross residuo e' non negativo e copre in valore
assoluto il net residuo. Il prefisso hash riportato nei nomi dei due export
coincide; senza i byte originali questo non costituisce una nuova verifica
crittografica della fotografia.

La verifica aritmetica richiesta e' quindi documentata attraverso il rapporto
dell'app reale e i controlli sugli export. Non e' stato eseguito nel runner
`scripts/verify_snapshot.py` sulla fotografia originale, che resta nel bucket
privato. Nessuna verifica locale dell'autenticita' della fonte viene dedotta
da questo rapporto.

## Nuovo archivio automatico privato

Il client Auth/Storage e il form Streamlit sono stati configurati dal proprietario;
questa sessione non ha eseguito modifiche remote al progetto Supabase. I test aggiuntivi simulano login,
rifiuto di un altro UID e ruoli privilegiati, rinnovo dei token, richieste di
elenco paginate, selezione delle sole fotografie raw, download GET, protezione
dei dati per visitatori anonimi, riuso nella sessione e pulizia al logout.
La suite completa passa su Python 3.12 e 3.14.9: 338 passati, 1 test reale saltato.
Le modalita' pubbliche restano caricamento locale e demo; l'automatismo richiede
login e resta disattivato senza configurazione e policy dedicate.
Non sono stati caricati nel repository il rapporto privato ricevuto o chiavi.

La policy e' stata inoltre eseguita su PostgreSQL 17.11 in un cluster locale
usa e getta, con socket privato e dati esclusivamente sintetici. Il comando
riproducibile e' `python scripts/test_reader_policy.py --pg-bin-dir DIR`.
Verificati: lettura raw per il solo UID, esclusione anonimi/altri utenti/log/replay,
INSERT e TRUNCATE rifiutati, UPDATE e DELETE con zero righe interessate,
accesso del writer proprietario invariato, rifiuto dei baseline non sicuri e
rollback della CREATE POLICY se la verifica successiva non riesce.
Questo test non e' una prova sul progetto Supabase di produzione.

Il successivo aggiornamento aggiunge un test di rifiuto dei risultati in caso di
mancata riconciliazione e verifica riuso del rapporto, cambio di modalita' e
pulizia al logout. I controlli usano la fotografia sintetica: non convertono il
test reale locale saltato in un controllo eseguito.


## Visualizzazione Future ES e differenziale condiviso

La prima versione riproduceva in Edge il calcolo indipendente Yahoo del
differenziale. Su richiesta del proprietario il percorso automatico e' stato
sostituito con la lettura dei metadati di `spx-snapshots/mt4/latest.csv`, gia'
pubblicato dal workflow esistente. Non viene eseguito codice Serafini o Yahoo,
non si avvia il publisher e non si analizzano i profili presenti dopo l'intestazione.
La sola trasformazione e' l'arrotondamento e la somma dell'offset ai prezzi.

I test verificano schema, date, valori, GET al singolo oggetto, Range limitato,
interruzione prima dei profili, errori senza segreti, isolamento anonimo,
aggiornamento dell'offset automatico, grafici e CSV/JSON, GEX SPX invariato e
pulizia al logout. Suite completa su Python 3.12 e 3.14: 338 passati e 1 test
reale locale saltato. L'utility Yahoo precedente e' coperta da test diagnostici,
ma un test Streamlit ne vieta l'invocazione durante la lettura condivisa.

La policy additiva e' stata testata su PostgreSQL locale usa e getta: un solo
file aggiuntivo leggibile al solo UID, nessun altro file MT4, nessun accesso per
anon/altri utenti, INSERT/TRUNCATE rifiutati e UPDATE/DELETE senza righe modificate.
La policy raw originaria rimane identica; il writer proprietario mantiene accesso.
Verificati installazione ripetibile, guard di baseline e rollback su errore.

GitHub riporta successo per il workflow MT4 esistente, ma non e' una lettura
Supabase eseguita come utente Edge. Restano da applicare il nuovo SELECT con lo
stesso UID e confermare la lettura reale nell'app. Nessuna credenziale privilegiata
e' presente nel runner. Nessuna modifica a repository, job, dati o link MT4 Serafini.
