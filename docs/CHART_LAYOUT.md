# Candele a sinistra e GEX verticale a destra

La vista usa una sola figura Plotly con due pannelli: candele a 5 minuti a
sinistra (65%) e profilo GEX a destra (35%). I prezzi crescono sull'asse verticale
comune; range iniziale, zoom e spostamento verticale sono allineati. Nel profilo
le barre si estendono orizzontalmente: Call positive verdi, Put negative rosse e
NET rosa. L'asse orizzontale del profilo resta GEX SPX in miliardi USD/1%.

Wall, flip, prezzo della fotografia e ultima quotazione disponibile hanno guide
orizzontali sui due pannelli. Zoom operativo e Vista completa restano disponibili.
Lo zoom operativo segue l'intervallo delle candele e l'ultimo prezzo disponibile,
con margine e almeno 80 punti di altezza. Include spot/wall/flip entro 100 punti
da tale intervallo; i livelli piu' lontani restano indicati sopra il grafico e
nella Vista completa. Senza candele o quotazione si centra sullo spot della
fotografia. Anche la scala orizzontale GEX segue gli strike inizialmente visibili:
barre lontane non schiacciano quelle vicine al prezzo. Tutti i dati delle tracce
restano presenti e la Vista completa mostra l'intero profilo.
L'offset ES si applica ai soli strike/livelli SPX: le candele ES=F sono gia' prezzi
future e non vengono traslate una seconda volta. Nessun prezzo di mercato entra
in analyze, verify_snapshot o nei calcoli del motore Edge.

## Fonte e storico

Le candele Yahoo usano barre a 5 minuti concluse e i timestamp sono mostrati in
ora italiana, con CET/CEST. Una quotazione valida puo' essere ritardata: orario,
ritardo dichiarato e dati datati restano visibili. Il refresh rilegge solo la
quotazione; non avvia acquisizioni CBOE o workflow Serafini.

Ultima disponibile usa il contesto di mercato piu' recente. Seleziona fotografia
storica usa invece la giornata selezionata in Italia e scarta prezzi/candele di
altri giorni, anche se i metadati Yahoo riportano una quotazione odierna. Sono
candele della giornata: possono comprendere barre successive alla fotografia e
non costituiscono una simulazione di cosa fosse noto all'ora dell'acquisizione.
L'orario di acquisizione non e' dedotto dal timestamp o dal nome del file CBOE.

Se Yahoo non risponde o la data supera lo storico disponibile, il pannello sinistro
lo segnala. Non vengono inventate candele o spacciato lo spot della fotografia per
prezzo corrente. La demo sintetica non richiede quotazioni esterne e mostra il
profilo di test con un pannello candele esplicitamente privo di dati reali.

La lettura prova query1 e, se fallisce o non fornisce candele, query2. Si tratta
di due endpoint Yahoo, non di due fonti indipendenti: possono essere indisponibili
entrambi. Ogni tentativo usa un client separato, solo GET, stesso ticker/periodo,
timeout limitato, TLS, nessun redirect e risposta massima 2 MiB. Un fallback
storico non sostituisce mai la giornata selezionata con dati odierni.

Se un refresh fallisce dopo una lettura riuscita nella stessa sessione e per lo
stesso ticker/periodo, restano visibili le ultime candele con un avviso esplicito
di mancato aggiornamento. Il loro timestamp originale resta invariato. Il
fallimento riduce la cache del tentativo a 30 secondi anziche' bloccare un errore
storico per un'ora; il pulsante forza subito una nuova lettura. Senza dati in
cache il pannello mostra la causa sicura dell'errore e nasconde l'asse temporale
vuoto, evitando numeri privi di significato. Logout elimina anche questi dati.

## Compatibilita' con gli aggiornamenti esistenti

La modifica parte da main af92f6e e conserva login prima dei controlli, 0DTE
predefinito e relativa correzione overnight, selettore storico, lettura del basis
gia' pubblicato, colori, download originale/CSV/JSON e distinzione fra timestamp
CBOE e acquisizione Serafini. Il prototipo locale precedente non e' sovrascritto.
Motore, lettore delle fotografie, permessi, dipendenze e job restano invariati.

I test controllano pannelli/assi, valori GEX immutati, assenza di doppio offset,
barre concluse, allineamento delle giornate, cambio CET/CEST, login, selezione
storica e cache dei calcoli al refresh del solo prezzo. I test UI precedenti sono
aggiornati per il default 0DTE e i controlli avanzati gia' presenti su main.

Il runner non raggiunge Yahoo attraverso il proxy: questi test non attestano
la disponibilita' delle candele reali nel deploy Streamlit. Non sono richiesti
nuovi Secrets o permessi Supabase. La fonte pubblica riceve solo ticker e periodo,
mai fotografie, livelli GEX o credenziali private.

Verifica del 25/10/2026: 365 test superati e 1 test reale locale saltato sia su
Python 3.12 sia su 3.14. Health HTTP e controllo WebSocket locale con demo
sintetica riusciti. Non e' una verifica browser o del provider reale online.

Correzione zoom del 26/10/2026: 368 test superati e 1 test reale locale saltato
su Python 3.12 e 3.14. Verificato in Chromium il rendering della figura con dati
esplicitamente simulati: candele leggibili, scale iniziali allineate, range dei
due assi prezzi ancora identici dopo uno zoom Plotly. Questa verifica locale
non attesta la disponibilita' delle quotazioni o l'aggiornamento online.

Resilienza lettura del 26/10/2026: 376 test superati e 1 test reale locale
saltato su Python 3.12 e 3.14. Testati con trasporti simulati fallback HTTP,
timeout, risposte invalide, ticker errato, quote senza candele, assenza di
cookie/credenziali e rispetto della giornata storica; l'interfaccia mantiene
timestamp e calcolo GEX durante un errore e riprende dopo il successivo successo.
Verificato in Chromium anche il pannello di errore simulato senza asse tempo
numerico. Le prove dirette del runner ai due endpoint falliscono al proxy:
la causa specifica osservata nel deploy non e' deducibile dallo screenshot e
il recupero delle candele reali online non e' ancora verificato.
