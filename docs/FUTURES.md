# Livelli SPX ed equivalenti Future ES

La visualizzazione Future ES applica una traslazione dei prezzi, separata dal
motore matematico Edge. Non calcola gamma di opzioni ES e non importa risultati,
codice o credenziali Serafini. Nessun repository, collector, dato, cron-job,
permesso Supabase o collegamento MT4 esistente viene modificato.

## Procedura del differenziale

Il comportamento richiesto e' quello di APP SPX, verificato in sola lettura su
[`es_spx_basis.py`](https://github.com/GrespoSan/Serafini-SPX-Dashboard/blob/2d8b558be8cf74f91a95bc062f90a477f8130e66/es_spx_basis.py)
e sulla relativa interfaccia `gamma_section.py` dello stesso commit:

1. Recuperare le chiusure non aggiustate Yahoo di ES=F e ^GSPC a 15 minuti.
2. Allineare per istante le due serie, senza interpolare barre mancanti.
3. Usare la piu' recente seduta comune strettamente precedente alla data della
   fotografia, limitandosi alle barre con timestamp 09:30 <= ora < 16:00 New York.
4. Esigere almeno 20 barre allineate, prima barra entro le 09:45 e ultima dalle
   15:30. Se la seduta precedente e' incompleta non ripiegare su una piu' vecchia.
5. Calcolare la media aritmetica di ES meno SPX e arrotondarla al punto intero
   con Decimal ROUND_HALF_UP, anche per differenziali negativi.
6. Sommare quel differenziale a spot equivalente, wall, tutti i gamma flip e
   coordinate dei grafici. NET/Gross GEX, regime e contratti restano SPX.

Per l'archivio la data target deriva dal nome del file, come in APP SPX; per
l'upload deriva dalla data UTC del payload. Il motore gamma mantiene invece
il proprio orologio di valutazione storico: la conversione non lo altera.

La lettura Yahoo usa direttamente gli endpoint pubblici chart impiegati per
le chiusure Yahoo, senza aggiungere yfinance alle dipendenze. L'intervallo di
richiesta e' quello di APP SPX: da target meno 10 giorni fino al minimo tra
target piu' 1 giorno e oggi piu' 1 giorno; storico oltre 50 giorni o target
oltre domani non vengono sostituiti con quotazioni odierne.

## Utilizzo

Per fotografie SPX reali il selettore parte da Future ES (equivalente). Una sola
acquisizione automatica viene tentata per data e sessione; Ricalcola ES − SPX
consente un nuovo tentativo. Il campo del differenziale e' modificabile e conserva
la precisione di eventuali correzioni manuali, come APP SPX. La correzione resta
legata a quella data e sessione; non viene riutilizzata su una giornata nuova.
In modalita' sintetica la vista iniziale e' SPX e non si cercano quotazioni reali.

Un link puo' precompilare un differenziale verificato tramite i parametri
`es_basis_date=AAAA-MM-GG` ed `es_basis=NUMERO`. Il valore viene accettato solo per
la data coincidente e non sovrascrive un valore gia' presente nella sessione.
I parametri sono preferenze di visualizzazione, non credenziali o segnali.

Se Yahoo fallisce o il campo e' vuoto/non valido, la vista resta chiaramente SPX,
senza assumere differenziale zero. Un valore zero inserito esplicitamente e'
consentito. Un ricalcolo fallito conserva l'eventuale correzione manuale.

ES=F e' il continuo Yahoo, che puo' differire da una scadenza CME specifica o dal
prezzo del broker. Spot equivalente ES e' SPX piu' differenziale storico, non una
quotazione corrente del future. Per uguagliare una correzione manuale di APP SPX,
inserire lo stesso differenziale verificato per la stessa giornata.

Il CSV ES conserva `strike_spx` e aggiunge `strike_es`, differenziale, data target,
fonte e, quando disponibile, data della seduta di riferimento. Il JSON mantiene
i risultati SPX originali e registra la visualizzazione in `display_conversion`.
Queste preferenze e i dati privati non vengono inseriti in cache globale.

## Verifica

Test con dati sintetici controllano allineamento, weekend, esclusione dei dati
di target e successivi, dati incompleti, fusi orari, arrotondamenti positivi e
negativi, errori Yahoo e date fuori storico. I test Streamlit verificano prezzi,
entrambi gli assi dei grafici, CSV/JSON, invarianza dei GEX originali, modifica
manuale, riuso per data e cancellazione al logout.

Il proxy del runner blocca Yahoo prima di raggiungere il provider: non e' stata
verificata qui la disponibilita' delle quotazioni reali. Il valore fornito dal
proprietario per la fotografia in uso permette comunque di verificare e mostrare
la traduzione senza inventare una stima automatica o modificare APP SPX.
