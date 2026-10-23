# Edge GEX Lab — clone indipendente

Il clone originale è stato recuperato dallo ZIP `SPX_Edge_GEX_Clone_Cloud_Pronto.zip`.
L'entrypoint Streamlit resta `edge_streamlit.py`. Il motore originale `gexlab/`
è conservato senza modifiche; wrapper e accesso agli archivi sono stati corretti.

Per istruzioni aggiornate, usare [README.md](README.md),
[pubblicazione](docs/DEPLOYMENT.md) e [provenienza](docs/IMPORT.md).
Richiede Python 3.12. L'app non usa codice o risultati Serafini, non avvia
cron-job, non modifica Supabase e non invia dati a MT4.

Il file reale citato nel test del vecchio clone,
`SPX_CBOE_20261014_135903.json.gz`, non è incluso nello ZIP ricevuto.
Le fixture incluse sono sintetiche e non sostituiscono tale verifica.
