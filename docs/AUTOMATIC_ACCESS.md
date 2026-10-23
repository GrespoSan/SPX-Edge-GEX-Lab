# Accesso automatico Edge: proposta e controllo preliminare

Stato: progettazione, non attivato. Nessuna modifica remota applicata a Supabase.
La richiesta successiva del proprietario e' semplificare e automatizzare l'accesso
senza compromettere i dati. Resta esclusa qualsiasi modifica alla metodologia
Serafini, ai suoi repository, cron-job e collegamento MT4.

## Risultato previsto

- Una configurazione iniziale, senza download manuali ad ogni fotografia.
- Accesso autenticato ai dati privati anche se l'interfaccia Edge e' pubblica.
- Individuazione dell'ultima fotografia SPX gia' archiviata, con timestamp visibile.
- Aggiornamento periodico mentre l'app e' aperta; al successivo accesso viene
  recuperata la fotografia disponibile piu' recente. Non e' un nuovo collector.
- Gestione del rinnovo della sessione senza inserire nuovi JWT o URL firmati
  ad ogni scadenza. Resta possibile dover rifare il login dopo logout o revoca.
- Elaborazione con il solo motore Edge, senza scritture a Storage, database o MT4.

## Vincoli di accesso

L'app pubblica non deve scaricare fotografie private usando un'identita'
condivisa e poi mostrarle a visitatori anonimi. Il controllo di accesso deve
precedere ogni lettura, aggiornamento, grafico e download dei dati privati.
Il caricamento locale e l'esempio sintetico possono restare pubblici.

Non riutilizzare service-role key, chiavi sb_secret_*, credenziali amministrative
o connessioni privilegiate di APP SPX. Non allargare le policy per anon o per
tutti gli utenti authenticated. Non modificare la policy che serve ad APP SPX
per darle indirettamente accesso a Edge.

Creare un account Auth ordinario e aggiungere SELECT al bucket non dimostra,
da solo, che quell'account sia di sola lettura: potrebbe ereditare scritture su
altre tabelle, accessi ad altri oggetti o funzioni SECURITY DEFINER eseguibili.
Prima di scegliere il meccanismo vanno esaminate le autorizzazioni effettive.
Il controllo locale dei claim JWT non sostituisce questo esame.

## Primo passo: controllo che non modifica il progetto

Eseguire `supabase/inspect_edge_access.sql` nel SQL Editor del progetto esistente.
Il comando usa una transazione READ ONLY e legge esclusivamente metadati di
sicurezza e nomi di fotografie, senza accedere a chiavi o password.
Non cambia utenti, ruoli, policy, bucket, cron-job o righe applicative.
I risultati vanno condivisi privatamente per la verifica, non commessi nel
repository pubblico. Non includere esportazioni di Secrets o credenziali.

L'analisi richiede poi di verificare i grant effettivi, compresi eventuali ruoli
ereditati e funzioni accessibili: il rapporto e' un punto di partenza, non una
certificazione completa dei privilegi.

## Configurazione da definire dopo il controllo

1. Identificare un accesso dedicato a Edge, applicando i limiti dal lato server:
   sola lettura/elenco delle fotografie SPX necessarie in spx-snapshots; nessun
   permesso di inserimento, aggiornamento o eliminazione, ne' accesso aggiuntivo
   alle risorse dell'applicazione esistente.
2. Definire eventuali aggiunte alle autorizzazioni come cambiamento separato,
   mirato e revisionabile. Non modificare o rimuovere le policy esistenti alla
   cieca; verificare che l'identita' di APP SPX mantenga gli stessi permessi.
3. Collegare la nuova autenticazione a Edge e rinnovare automaticamente la
   sessione. Le credenziali restano fuori da Git e non vengono chieste in chat.
4. Usare l'effettiva struttura delle cartelle per selezionare l'ultima fotografia
   con paginazione e limiti di richieste, evitando di scaricare tutto il bucket.
   Il timestamp del payload resta la fonte per la valutazione matematica.
5. Verificare accessi autorizzati e rifiutati senza tentare scritture sui dati
   esistenti. Eseguire le prove di scrittura negate soltanto in un ambiente di
   test isolato, oltre all'ispezione dei privilegi di produzione.
6. Confrontare un calcolo su una fotografia reale e verificare la lettura
   automatica online prima di dichiarare l'integrazione completata.

Non sono ancora stati eseguiti questi passi: mancano una sessione amministrativa
Supabase accessibile e i risultati del controllo dei permessi. La soluzione
finale non deve dipendere da rinnovi manuali periodici di token o URL firmati.
