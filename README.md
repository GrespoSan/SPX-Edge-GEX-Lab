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
È stata verificata anche la compatibilità con Python 3.14.9, presente nel
deploy Community Cloud. PyArrow è fissato a 24.0.0 per evitare la versione 26
che Cloud segnala come affetta da un crash noto.
Le versioni dirette e transitive sono fissate in `requirements.txt` e
`constraints.txt`; `requirements-edge.txt` resta un alias compatibile.

La modalità di caricamento `.json` / `.json.gz` funziona senza credenziali o rete.
L'esempio incluso è **sintetico**, sempre etichettato come tale.
Il wrapper accetta catene indice SPX o NDX riconoscibili dai contratti OCC.
Non sono implementate nel wrapper le catene ETF SPY/QQQ.

## Fotografie private e Supabase

L'archivio automatico usa un'utenza dedicata a Edge con SELECT sulle sole
fotografie grezze SPX. Il bucket `spx-snapshots` resta privato. L'app pubblica
richiede login prima di leggere, mostrare o scaricare quei dati; le sessioni
sono isolate e non usano cache globali per le fotografie.

Dopo una configurazione iniziale, l'app seleziona l'ultima fotografia nella
settimana di archivio piu' recente disponibile e controlla gli aggiornamenti
ogni due minuti mentre la pagina e' aperta. La sessione viene rinnovata senza
copiare JWT o URL firmati. Il motore non avvia cron o acquisizioni CBOE live.

La configurazione reale e' ancora da attivare. Seguire
[la procedura iniziale](docs/AUTOMATIC_ACCESS.md) e
[il modello dei Secrets](.streamlit/secrets.toml.example).
Sono vietate credenziali privilegiate; password e token non vanno nel repository
ne' in chat. I vecchi Secrets con token condiviso o URL firmato non vengono usati
dall'interfaccia pubblica.


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

Con il servizio Streamlit avviato, è disponibile anche un controllo attraverso
la connessione WebSocket effettiva:

```bash
.venv/bin/python scripts/check_streamlit.py --base-url http://127.0.0.1:8501
```

Verifica pagina iniziale e calcolo sintetico sul protocollo del server;
non verifica il rendering JavaScript del browser o una fotografia reale.

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

[App Edge online](https://spx-edge-gex-lab-djvbrdhckns6fv4exbgxos.streamlit.app/):
il proprietario ha confermato il funzionamento con login dedicato, lettura privata
e risultati su una fotografia SPX reale. L'archivio richiede autenticazione;
caricamento locale ed esempio sintetico restano accessibili senza credenziali.
Vedere [verifiche e limiti](docs/VALIDATION.md) per distinguere questa prova dai
test locali e dal successivo confronto aritmetico automatico.
