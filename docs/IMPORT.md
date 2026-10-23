# Provenienza del codice Edge

Importato dall'archivio fornito dall'utente:
`SPX_Edge_GEX_Clone_Cloud_Pronto.zip`, directory interna `Edge-GEX-Lab-main/`.

SHA-256 dell'archivio:

```text
cbc043c8ba3983db6a01361fe62be2eec4ec43080692c5a906b6679e0400a692
```

Il README originale identifica il progetto upstream come
`simonro/Edge-GEX-Lab`, autore/licenza MIT Tape to Edge. Lo ZIP non contiene
metadati Git: non viene attribuito un commit upstream non verificato.
La licenza è conservata in `LICENSE`, il README in `README_UPSTREAM.md`.
I **25 file Python di `gexlab/`** sono stati confrontati byte per byte con lo ZIP
e sono invariati. Sono conservati anche test e fixture originali e il frontend.
Le immagini e fixture upstream sono dichiarate sintetiche dall'autore.

## Correzioni del clone Streamlit

- Dipendenze dirette e transitive fissate per Python 3.12; separate runtime e
  sviluppo. Nessuna dipendenza Node o backend API necessaria al deploy Streamlit.
- Nessun errore di avvio se il file Secrets non esiste.
- Eliminato l'accesso remoto automatico per elencare il bucket. Download soltanto
  con GET di un oggetto scelto o di un URL firmato già disponibile.
- Rifiuto di credenziali privilegiate note e vincolo a HTTPS/Supabase/bucket atteso;
  redirect disabilitati ed errori senza segreti o URL.
- Rimossa la cache condivisa dei dati privati; stato conservato solo per sessione
  e invalidato al cambio di sorgente, percorso o credenziali.
- Timestamp storico conservato, con controlli su schema, simbolo, duplicati,
  prezzo, OI, IV e dimensione del contenuto decompresso.
- Selezione delle quattro date dopo la rimozione dei contratti già regolati.
- Calendario XNYS locale con festività e chiusure anticipate al posto dei soli
  giorni feriali. È dichiarato come proxy, non calendario ufficiale CBOE.
- Il wrapper supporta gli indici SPX/NDX riconosciuti dal parser originale:
  rimosse le indicazioni inesatte di supporto ETF nel clone Streamlit.
- Risultati con unità esplicite, copertura, calendario, data OI inferita e hash;
  esempio sintetico e controlli aritmetici separati dai test sui dati reali.
- Script Windows adattati all'app Streamlit senza avvio dei feed live.

Il vecchio `test_edge_clone.py` terminava con successo se mancava un file
sotto `/mnt/data`. Il test è sostituito da un test esplicitamente saltato se
`EDGE_REAL_SNAPSHOT_PATH` non è configurato. Il file menzionato dal test,
`SPX_CBOE_20261014_135903.json.gz`, **non è incluso** nell'archivio.

Non sono state apportate modifiche a repository Serafini, Supabase, cron-job
oppure MT4. Non sono state eseguite richieste remote a Supabase in questa verifica.
