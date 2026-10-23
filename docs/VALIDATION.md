# Verifiche e stato di pubblicazione

Verifiche nell'ambiente di sviluppo, 23 ottobre 2026, Python 3.12.14:

| Controllo | Esito |
| --- | --- |
| Installazione runtime e sviluppo | Completata, dipendenze fissate con constraints |
| Ambiente pulito con solo `requirements.txt` | Avvio e calcolo sintetico Streamlit verificati senza FastAPI o pytest |
| `python -m pip check` | Nessuna incompatibilità rilevata |
| Suite originale Edge | 212 test passati |
| Suite completa, inclusi wrapper, Storage e Streamlit | 289 passati, 1 saltato |
| Stessa suite con Python 3.14.9 e PyArrow 24.0.0 | 289 passati, 1 saltato |
| Test reale SPX | Saltato esplicitamente: fotografia assente |
| Verifica scalare indipendente sul nuovo esempio sintetico | 40 contratti, NET e gross riconciliati |
| Streamlit AppTest | Avvio senza Secrets, calcolo sintetico nelle tre modalità, sorgenti non configurate |
| Processo Streamlit locale | Home HTTP 200; health HTTP 200 con risposta `ok` |
| Protocollo WebSocket reale su Python 3.14.9 | Pagina iniziale e cinque metriche sintetiche ricevute, bind predefinito dual-stack |
| Frontend originale, Node.js 24.19.0 | `npm ci` e `npm run build` completati |
| Codice originale `gexlab/` | 25 file Python identici allo ZIP |
| Richieste Supabase reali | Non eseguite: accesso di sola lettura non disponibile |
| Streamlit Community Cloud | Deploy avviato dal proprietario, server partito secondo il log; caricamento infinito segnalato nel browser, URL non verificabile dal runner |

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
online non è quindi confermato. Servono il nuovo esito dopo il riavvio Edge e,
se il caricamento persiste, il messaggio della pagina o della console del browser.

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

## Passaggi che richiedono materiali o accessi esterni

1. Fornire una fotografia SPX CBOE reale autorizzata. Il proprietario ha confermato
   che non è disponibile un accesso Supabase di sola lettura: integrazione
   remota lasciata disattivata, senza aggiungere requisiti di credenziali.
2. Il proprietario deve verificare i privilegi della credenziale esistente;
   non sono autorizzate modifiche al progetto Supabase.
3. Il proprietario ha creato l'app nel proprio account Streamlit. Questa sessione
   non dispone di accesso alla gestione Streamlit per riavviarla o ispezionare
   direttamente i log del deploy.
4. Verificare poi l'URL effettivo con accesso, fotografia e calcolo.

Il permesso di lavorare e caricare codice nel repository Edge è già stato dato.
Non occorre una nuova conferma generica per proseguire lo sviluppo. Questi blocchi
riguardano materiali, credenziali o sessioni esterne non presenti nell'ambiente.


## Nuovo archivio automatico privato

Il client Auth/Storage e il form Streamlit sono predisposti ma il progetto reale
non e' stato configurato da questa sessione. I 21 test aggiuntivi simulano login,
rifiuto di un altro UID e ruoli privilegiati, rinnovo dei token, richieste di
elenco paginate, selezione delle sole fotografie raw, download GET, protezione
dei dati per visitatori anonimi, riuso nella sessione e pulizia al logout.
La suite completa passa su Python 3.12 e 3.14.9: 289 passati, 1 test reale saltato.
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
