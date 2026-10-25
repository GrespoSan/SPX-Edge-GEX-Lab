# Candele a sinistra e GEX verticale a destra

La vista usa una sola figura Plotly con due pannelli: candele a 5 minuti a
sinistra (65%) e profilo GEX a destra (35%). I prezzi crescono sull'asse verticale
comune; range iniziale, zoom e spostamento verticale sono allineati. Nel profilo
le barre si estendono orizzontalmente: Call positive verdi, Put negative rosse e
NET rosa. L'asse orizzontale del profilo resta GEX SPX in miliardi USD/1%.

Wall, flip, prezzo della fotografia e ultima quotazione disponibile hanno guide
orizzontali sui due pannelli. Zoom operativo e Vista completa restano disponibili.
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
