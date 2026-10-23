# SPX Edge GEX Lab

Applicazione Streamlit autonoma per analizzare fotografie CBOE già archiviate.
Usa il motore matematico originale Edge (`gexlab`), incluso con licenza MIT.
**Non modifica e non integra Serafini, i suoi calcoli, cron-job, Supabase o MT4.**

## Avvio

Python **3.12**. Dalla radice del repository:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m streamlit run edge_streamlit.py
```

Su Windows: `setup.bat`, poi `launch.bat`; oppure usare
`.venv\Scripts\python.exe` al posto di `.venv/bin/python`.
Il percorso ufficiale dell'app cloud è **`edge_streamlit.py`**.
Node.js e il backend FastAPI non servono all'app Streamlit.
Le versioni dirette e transitive sono fissate in `requirements.txt` e
`constraints.txt`; `requirements-edge.txt` resta un alias compatibile.

La modalità di caricamento `.json` / `.json.gz` funziona senza credenziali o rete.
L'esempio incluso è **sintetico**, sempre etichettato come tale.
Il wrapper accetta catene indice SPX o NDX riconoscibili dai contratti OCC.
Non sono implementate nel wrapper le catene ETF SPY/QQQ.

## Fotografie private e Supabase

Il bucket `spx-snapshots` resta privato. La lettura remota è facoltativa e parte
solo premendo il pulsante di lettura; non viene avviato alcun feed live.
L'app esegue soltanto GET del singolo oggetto richiesto: non elenca oggetti,
non emette URL firmati, non scrive e non cambia le policy.

Sono supportati un URL firmato **già emesso**, oppure un'identità **già esistente**
con privilegi di sola lettura verificati dal proprietario. Le credenziali
privilegiate note (`service_role`, `sb_secret_*`, ruoli amministrativi) sono
rifiutate prima della richiesta. Questo controllo locale non prova i privilegi
RLS di un'identità: la verifica spetta al proprietario e non richiede tentativi
reali di scrittura. Senza accesso compatibile, usare il caricamento locale.

Configurare le credenziali solo nei Secrets della nuova app o in un file locale
`.streamlit/secrets.toml`, escluso da Git. Non inviare chiavi in chat.
Vedere [pubblicazione e configurazione](docs/DEPLOYMENT.md) e
[modello dei Secrets](.streamlit/secrets.toml.example).
Dati e risposte private restano nella sessione dell'utente; non viene usata una
cache Streamlit condivisa. Limitare la visibilità dell'app agli utenti
che hanno diritto di vedere le fotografie prima di abilitare la lettura remota.

## Metodo

Il codice in `gexlab/` è identico a quello nello ZIP fornito. Il wrapper lo usa
senza importare formule o risultati Serafini:

- Gamma Black–Scholes, `r = q = 0`.
- `GEX = segno × gamma × OI × 100 × spot² × 0,01`, USD per movimento dell'1%.
- Call positive, put negative: assunzione di posizionamento, non dato osservato.
- Finestra originale: 0–7 giorni di calendario; acquisizione strike ±20%, wall
  e grafico strike ±10%, copertura GEX stimata entro ±5%.
- Valutazione al timestamp storico della fotografia o alla chiusura secondo le
  regole Edge, mai alla data attuale.
- Radici SPX/NDX AM alle 09:30 New York; SPXW/NDXP PM alla chiusura di sessione.
- Calendario locale `exchange_calendars:XNYS`, con festività e chiusure anticipate:
  è un proxy delle sessioni USA, non il calendario ufficiale dei regolamenti CBOE.
- La data dell'OI è inferita, non pubblicata da CBOE.

Si possono scegliere 0DTE, le prossime quattro date **non già regolate**, oppure
tutte quelle disponibili nella finestra Edge. Se ce ne sono meno di quattro,
l'app mostra soltanto quelle effettive. Copertura insufficiente o non stimabile
viene segnalata. L'analisi non attesta l'idoneità operativa di un segnale.

## Test e verifica

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests -q -p no:cacheprovider
.venv/bin/python scripts/verify_snapshot.py fixtures/synthetic_cboe_spx.json
```

Per una fotografia **reale autorizzata**, conservarla in `local-data/` (esclusa
da Git), quindi:

```bash
EDGE_REAL_SNAPSHOT_PATH=local-data/SPX_CBOE.json.gz .venv/bin/python -m pytest tests/test_edge_real_snapshot.py -q
.venv/bin/python scripts/verify_snapshot.py local-data/SPX_CBOE.json.gz --output local-data/verification.json
```

Il controllo scalare indipendente confronta gamma/GEX per contratto, NET e gross
GEX con l'aritmetica Edge; riusa selezione e tempo di valutazione del wrapper.
Non dimostra l'autenticità della fotografia né la correttezza dei dati di mercato.
Il test reale è dichiarato **skipped** se il file non è fornito.

Il frontend originale React è conservato per completezza. La build opzionale
usa Node.js 24: `cd web`, `npm ci`, `npm run build`. L'app cloud non lo richiede.
Non avviare i feed live descritti nella documentazione upstream per questo flusso.

## Provenienza e stato

- [Importazione dallo ZIP e correzioni](docs/IMPORT.md)
- [Verifiche eseguite e limiti](docs/VALIDATION.md)
- [Pubblicazione separata su Streamlit](docs/DEPLOYMENT.md)
- [Documentazione originale upstream, conservata come riferimento](README_UPSTREAM.md)
- [Licenza originale MIT](LICENSE)

La presenza del codice e dei test nel repository **non attesta una pubblicazione
online**: questa richiede un deploy separato e la verifica del suo URL effettivo.
