# Archivio SPX automatico e privato per Edge

Stato: il proprietario ha applicato la policy dedicata, configurato i Secrets e
mostrato l'app autenticata con risultati su una fotografia reale. Il successivo
rapporto JSON conferma il controllo scalare su tutti i 1.739 contratti validi,
con NET e Gross riconciliati; il rapporto e il CSV sono stati esaminati nel runner.
Il runner non ha applicato modifiche al progetto Supabase.
Vedere [verifiche e limiti](VALIDATION.md).

## Configurazione iniziale, una volta

1. Nel progetto Supabase esistente, Authentication > Users > Add user > Create
   new user: creare un'utenza nuova destinata solo a Edge. Usare un'email propria,
   una password riservata e la conferma email. Non modificare utenti di APP SPX.
2. Copiare il solo User UID. Non comunicare password, chiavi amministrative,
   token di sessione o service-role key in chat o nel repository.
3. Revisionare `supabase/enable_edge_reader.sql`, sostituendo il placeholder UUID
   con l'ID appena creato. Eseguire la query nel SQL Editor del progetto.
   La query aggiunge una sola policy SELECT riferita a quell'ID e ai soli file
   `AAAA-Wxx/snapshots/SPX_CBOE_AAAAMMGG_HHMMSS.json[.gz]` in spx-snapshots.
   Non modifica policy esistenti, dati, ruoli, bucket, calcoli o cron-job.
4. Se una verifica della query fallisce, fermarsi e condividere il messaggio:
   non eliminare o allargare le protezioni per farla passare. La transazione
   esegue rollback su errore. Se la policy esiste gia', si ferma senza sostituirla.
5. Nei Secrets della sola app Streamlit Edge configurare:

   ```toml
   SUPABASE_URL = "https://PROJECT.supabase.co"
   SUPABASE_ANON_KEY = "CHIAVE_PUBLISHABLE_O_ANON"
   EDGE_READER_USER_ID = "UUID_UTENTE_EDGE"
   EDGE_ARCHIVE_ENABLED = true
   ```

   Inserire i valori effettivi solo nel pannello Secrets. La chiave deve essere
   publishable/anon, mai service_role o sb_secret_*. La password dell'utenza Edge
   non va nei Secrets: viene inserita nel form di login dell'app.
6. Aprire Edge, scegliere Archivio SPX automatico e accedere con email e password
   dell'utenza dedicata. L'app ricorda l'accesso nella sessione e rinnova i JWT;
   non servono download, token copiati o link firmati rinnovati a mano.

## Comportamento automatico

Per leggere anche il differenziale ES-SPX gia' pubblicato, eseguire una volta
`supabase/enable_edge_shared_basis.sql` con lo stesso UID. Aggiunge solo SELECT
su `mt4/latest.csv`, senza cambiare la policy delle fotografie o i Secrets.
Il file e il publisher esistenti restano invariati; Edge ne legge solo i metadati.
La fonte condivisa non e' ancora stata verificata online come lettore Edge.

La cartella settimanale piu' recente viene cercata nell'elenco del bucket. Nella
prima settimana con fotografie grezze SPX viene selezionato il file con stamp
nel nome piu' recente. Non vengono letti logs, replay o profili del motore Serafini. Dal feed condiviso
sono letti soltanto i metadati del differenziale, senza analizzare la tabella dei livelli.
Le pagine dell'elenco sono ordinate e paginate, con un limite che produce un
messaggio di errore anziche' scegliere da un risultato incompleto.
Il timestamp del payload resta il riferimento del motore matematico.

Ogni due minuti, mentre la pagina e' aperta, la sessione controlla nuovi file.
Un file con stesso percorso e updated_at viene riutilizzato nella sola sessione;
se cambia, viene scaricato nuovamente. E' disponibile anche Aggiorna ora.
Non vengono creati cron-job o collector; ad app chiusa non ci sono nuovi poll.
Un riavvio, logout o revoca puo' richiedere un nuovo login.

I visitatori anonimi vedono solo il form di accesso o le modalita' pubbliche di
caricamento locale ed esempio sintetico. Nessun dato privato e' conservato in
cache globale. Esci da Edge elimina token e dati della sessione locale; per
revocare un account definitivamente usare gli strumenti Auth del proprietario.

## Permessi e limiti della verifica

Il rapporto fornito dal proprietario conferma bucket privato, RLS attiva su
storage.objects e nessuna policy esistente su tale tabella. I grant SQL di
INSERT/UPDATE/DELETE ai ruoli anon/authenticated sono generici e non dimostrano
accesso effettivo: in assenza di policy le operazioni sono negate da RLS.
Aggiungere solo SELECT al singolo UID non abilita scritture agli oggetti.

La query verifica che questo stato non sia cambiato, che il nuovo utente sia
confermato e non privilegiato e che non risultino altre concessioni di scrittura
o funzioni SECURITY DEFINER da esaminare. Prova le letture con il ruolo e UID
esatti, esclude altri oggetti e verifica il mancato accesso per un altro UID.
Non prova scritture reali contro gli oggetti di produzione.

L'installazione, i Secrets e la lettura reale sono stati confermati dalle
schermate del proprietario. Il successivo rapporto JSON dell'app conferma anche
la verifica aritmetica, esaminata insieme al CSV senza condividere credenziali
o scaricare manualmente la catena dal pannello Supabase. Non e' ancora stato
osservato online l'arrivo di una fotografia successiva; il relativo comportamento
e' coperto da test simulati. Il runner non dispone dei byte originali della
fotografia e non presenta i controlli sugli export come un nuovo calcolo locale.
La modifica alle autorizzazioni e' limitata al nuovo lettore: metodologia,
repository, account esistenti, cron-job e collegamento MT4 Serafini restano fuori
ambito. Non e' necessario rendere pubblico il bucket.
