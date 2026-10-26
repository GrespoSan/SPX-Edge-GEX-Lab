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

La lettura usa prima `yfinance.download`, lo stesso metodo pubblico osservato
nel [lettore del replay APP SPX](https://github.com/GrespoSan/Serafini-SPX-Dashboard/blob/518c91ae61556f0c88ee2892c82d40c1a7dbffbf/replay_prices.py).
Il sorgente e' stato consultato in sola lettura. Edge ha un adattatore proprio,
senza importare il modulo, formule o profili dell'altra app. Per lo storico usa
la stessa finestra allargata intorno alla data e filtra poi le chiusure nella
giornata italiana selezionata e non oltre l'ora attuale. Per l'ultima vista
chiede 5 giorni e mantiene le ultime 72 barre concluse. Normalizza anche colonne
MultiIndex, valida ticker, OHLC e fuso orario, poi riutilizza il parser Edge.
Il prezzo esposto da questa lettura e' l'ultima chiusura 5m disponibile, con il
suo timestamp originale, senza una richiesta aggiuntiva di quotazione.

Se la libreria non restituisce dati validi, il fallback GET diretto prova query1
e query2 con lo stesso ticker/periodo, timeout, TLS, nessun redirect e risposta
massima 2 MiB per endpoint. I due client diretti non condividono cookie. Sono
sempre accessi a Yahoo, non fonti indipendenti, e possono fallire tutti. Un
fallback storico non sostituisce mai la giornata con dati odierni.

Una cache Streamlit condivisa di 5 minuti, con al massimo 32 combinazioni di
ticker/data, contiene esclusivamente OHLC e messaggi sicuri del provider
pubblico. Non riceve credenziali, fotografie, livelli o identificativi privati.
Memorizza anche gli esiti negativi per limitare richieste durante un HTTP 429.
Il pulsante Rileggi invalida solo la combinazione pubblica in uso; non svuota
le altre giornate o avvia lavori APP SPX. Le dipendenze yfinance/curl_cffi e le
relative dipendenze sono versionate nei requirements/constraints Edge.

Se un refresh fallisce dopo una lettura riuscita nella stessa sessione e per lo
stesso ticker/periodo, restano visibili le ultime candele con un avviso esplicito
di mancato aggiornamento. Il loro timestamp originale resta invariato. Il
fallimento riduce il controllo della sessione a 30 secondi; la cache pubblica
mantiene il periodo di 5 minuti e il pulsante forza subito una nuova lettura.
Senza dati in
cache il pannello mostra la causa sicura dell'errore e nasconde l'asse temporale
vuoto, evitando numeri privi di significato. Logout elimina questi dati di
sessione; la cache pubblica OHLC, priva di legami con l'utenza, scade con il TTL.

## Compatibilita' con gli aggiornamenti esistenti

La modifica parte da main af92f6e e conserva login prima dei controlli, 0DTE
predefinito e relativa correzione overnight, selettore storico, lettura del basis
gia' pubblicato, colori, download originale/CSV/JSON e distinzione fra timestamp
CBOE e acquisizione Serafini. Il prototipo locale precedente non e' sovrascritto.
Motore, lettore delle fotografie, permessi e job restano invariati. Le sole
nuove dipendenze riguardano il lettore pubblico delle candele.

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
cookie/credenziali nei fallback e rispetto della giornata storica; l'interfaccia mantiene
timestamp e calcolo GEX durante un errore e riprende dopo il successivo successo.
Verificato in Chromium anche il pannello di errore simulato senza asse tempo
numerico. Le prove dirette del runner ai due endpoint falliscono al proxy:
lo screenshot successivo del proprietario conferma HTTP 429 nel deploy. Il
recupero delle candele reali online non e' ancora verificato.

Allineamento lettore pubblico del 26/10/2026: 389 test superati e 1 test reale
locale saltato su Python 3.12 e 3.14, dipendenze installate e controllate su
entrambi. Verificati MultiIndex, assenza di timestamp inventati, esclusione
barre aperte, giornata storica, fallback e cache pubblica anche degli errori.
La prova diretta yfinance del runner non ottiene quotazioni utilizzabili; il
recupero nel deploy Edge resta da verificare, anche se il replay APP SPX mostra
candele. Un blocco Yahoo puo' dipendere dal server ed essere diverso fra app.

Altezza del 26/10/2026: grafico portato da 620 a 760 pixel, mantenendo lo stesso
intervallo prezzi e l'allineamento dei due pannelli. Il grafico e' circa il 23%
piu' alto: piu' spazio per candele e barre senza aggiungere strike o allargare
la scala. Nove test grafici superati e rendering locale controllato in Chromium
con dati simulati. Lo screenshot successivo del proprietario mostra le
candele reali anche in Edge dopo il cambio del lettore pubblico.
