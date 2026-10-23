# Livelli SPX ed equivalenti Future ES

La vista ES trasla soltanto le coordinate di prezzo. Il motore gamma originale
Edge continua a usare esclusivamente la fotografia CBOE SPX; non importa livelli,
profili o risultati del motore Serafini. NET/Gross GEX e regime restano SPX.

## Fonte gia' disponibile: lettura, senza ricalcolo

Il publisher esistente usa il branch `feature/mt4-replay-bridge` di APP SPX e
pubblica il file privato `spx-snapshots/mt4/latest.csv`. Il formato e' documentato
nel codice di [mt4_feed.py](https://github.com/GrespoSan/Serafini-SPX-Dashboard/blob/1e41532fb85169733b0d99c60b3c74623d7eac53/mt4_feed.py).
L'intestazione comprende `basis_es_spx`, `basis_date`, `date_rome`,
`basis_source` e `published_utc`. Edge legge questi metadati gia' pubblicati.
Non esegue `mt4_feed.py`, non avvia il workflow, non chiama la funzione Serafini
ES-SPX e non scarica barre Yahoo per la conversione automatica.
Le correzioni manuali del campo nella Dashboard restano nella sessione di
quell'app e non aggiornano il feed: Edge legge il differenziale pubblicato dal
publisher esistente, non il widget di un'altra sessione Streamlit.

La richiesta e' un solo GET autenticato al percorso fisso, con Range sui primi
8 KiB. Il lettore interrompe la lettura all'intestazione della tabella e non
analizza le righe `strike_spx`, `price_es`, `net_gamma` o gli altri profili.
Nessuna chiave privilegiata o cache globale: usa la sessione del lettore Edge.

Il publisher e il collegamento MT4 restano invariati. L'unica modifica necessaria
ai permessi e' una policy SELECT aggiuntiva per l'utente Edge e il solo oggetto
`mt4/latest.csv`: [SQL di attivazione](../supabase/enable_edge_shared_basis.sql).
La policy non estende l'accesso ad altri file MT4, bucket, log o replay e non
modifica la policy delle fotografie. La transazione verifica il baseline e le
letture effettive, e fa rollback su errore. Un secondo avvio valido e' innocuo.

## Data e applicazione

`date_rome` deve coincidere con la data della fotografia: per l'archivio questa
proviene dal nome del file, come in APP SPX; per l'upload dalla data UTC del
payload. `basis_date` deve precederla. Si controllano schema v3, metadati univoci,
valori finiti e data di pubblicazione coerente e non futura. Un feed di un altro
giorno non viene applicato alla fotografia corrente.

Il differenziale pubblicato ha sei decimali. Per mantenere la convenzione della
Dashboard si arrotonda questo numero al punto intero con Decimal ROUND_HALF_UP,
anche per valori negativi. Si somma poi lo stesso offset a spot equivalente,
wall, tutti i gamma flip e assi dei grafici. Non si ricalcola alcun gamma o GEX.

Il file `latest.csv` viene sostituito dal publisher esistente: non garantisce
uno storico dei differenziali. Per fotografie di altri giorni Edge non ricava
un valore da quotazioni odierne. Eventuali correzioni manuali restano legate alla
sola data e vengono dichiarate come manuali nel rapporto.

## Interfaccia ed export

Per fotografie SPX reali il selettore parte da Future ES (equivalente). Mentre
Archivio SPX automatico e' aperto, Edge rilegge i metadati ogni due minuti e
aggiorna l'offset automatico. Rileggi ES − SPX forza una nuova lettura, senza
avviare il publisher. Le correzioni manuali sono conservate finche' non si
richiede esplicitamente la rilettura con successo.

Se permesso, file o metadati validi mancano, l'offset automatico viene rimosso e
i valori restano esplicitamente SPX. Non si assume zero. L'upload pubblico senza
login puo' usare una correzione manuale, ma non accede al feed privato. La demo
non effettua letture esterne. I vecchi link con offset non sovrascrivono la
lettura automatica privata. I risultati Yahoo di una vecchia sessione sono scartati.

Il CSV ES conserva strike SPX e aggiunge strike ES, offset, date e fonte. Il JSON
mantiene i risultati originali SPX e aggiunge `display_conversion`, con i soli
metadati di conversione. Logout elimina metadati e preferenze private.

ES=F e' il continuo usato dal publisher, che puo' differire da una scadenza CME
specifica o dal broker. Lo spot equivalente e' SPX piu' differenziale storico,
non una quotazione corrente del future.

## Stato di verifica

Il workflow MT4 gia' esistente risulta completato con successo su GitHub. Il
runner non ha eseguito workflow, modificato repository Serafini o letto il file
privato con credenziali amministrative. La successiva schermata del proprietario conferma la lettura reale in Edge:
mostra differenziale pubblicato, riferimento, pubblicazione e fonte dell'archivio
condiviso. Il runner continua a non disporre della sessione privata.
Test HTTP simulati verificano lettura dell'intestazione, rifiuto di date diverse
e metadati errati, nessun accesso anonimo e nessuna chiamata Yahoo dall'interfaccia.
Il test PostgreSQL locale verifica policy, isolamento, assenza di scritture e
accesso del writer esistente invariato. Il lettore Yahoo precedente rimane solo
come utility diagnostica testata; non viene chiamato dal percorso automatico.
