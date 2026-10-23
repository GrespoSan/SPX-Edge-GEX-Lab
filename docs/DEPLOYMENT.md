# SPX Edge GEX Lab — preparazione della pubblicazione

## Stato verificato

Il repository originale contiene soltanto `README.md` e `NOTES.txt`.
Il codice Edge, il clone citato nella conversazione «Progetto parallelo Edge
GEX Lab», le dipendenze e una fotografia CBOE non sono disponibili nel checkout.
Questo documento prepara la pubblicazione: non attesta un'applicazione
implementata, un calcolo validato o una pubblicazione eseguita.

## Separazione obbligatoria

- Lavorare esclusivamente su `GrespoSan/SPX-Edge-GEX-Lab`.
- Non modificare la procedura Serafini, i suoi repository, i calcoli, i cron-job,
  il progetto Supabase esistente o il collegamento MT4.
- Il motore matematico Edge deve essere indipendente. Recuperare le formule e
  le convenzioni dalla conversazione originale prima di implementarle.
- L'unica integrazione consentita è la lettura delle fotografie CBOE già
  archiviate nel bucket privato `spx-snapshots`.

## Materiali necessari per completare lo sviluppo

1. Esportazione o link condiviso accessibile della conversazione di riferimento,
   con il codice originale e gli allegati del clone.
2. Una fotografia reale SPX CBOE autorizzata per la verifica e il suo contesto
   temporale; non pubblicare dati privati nel repository.
3. La modalità di lettura già autorizzata per il bucket, senza comunicare
   credenziali in chat o inserirle in Git.
4. Accesso del proprietario a Streamlit Community Cloud e al repository Edge.

## Accesso Supabase esclusivamente in lettura

Riutilizzare soltanto autorizzazioni esistenti. Non creare utenti, ruoli,
policy, bucket, tabelle, funzioni o processi nel progetto Supabase esistente.
Non rendere pubblico il bucket.

Modalità ammissibili, da verificare con il proprietario:

- Un URL firmato per una fotografia specifica, già fornito da un soggetto
  autorizzato, con scadenza e ambito limitati. Trattare l'intero URL come un
  segreto e verificare che sia utilizzabile dall'app distribuita. L'app Edge
  non deve ricevere la chiave necessaria a generare gli URL.
- Un'identità esistente con privilegi limitati alla lettura degli oggetti
  necessari. Una chiave publishable/anon, da sola, non prova l'accesso al bucket
  privato: verificare anche autenticazione e policy già presenti. Se i permessi
  non sono sufficienti, fermare l'integrazione senza modificare Supabase.

Non usare chiavi `service_role`, chiavi segrete amministrative, credenziali del
database o account che abbiano privilegi di scrittura. Impiegare solo richieste
di lettura; non testare i privilegi tentando upload, cancellazioni o modifiche.
Il successo di un download non dimostra da solo che una credenziale sia di sola
lettura: occorre anche la conferma del suo ambito autorizzativo.

Tenere segreti e URL firmati nelle impostazioni Secrets di Streamlit Community
Cloud. In locale, `.streamlit/secrets.toml` è escluso da Git. Non registrarli nei
log, negli errori mostrati all'utente o nella cache pubblica. Non inserire
fotografie private nel repository; `local-data/` è esclusa da Git. Limitare
l'accesso all'app agli utenti autorizzati a vedere i dati prima di collegare il
bucket privato.

Se non esiste una modalità compatibile con questi vincoli, la lettura del
bucket rimane bloccata. Un file fornito dal proprietario può consentire una
verifica matematica locale, ma non dimostra l'integrazione con Supabase.

## Verifica del motore Edge dopo il recupero

Documentare e testare le convenzioni effettivamente previste dal modello
originale: schema e unità CBOE, sottostante SPX, prezzo spot, timestamp e fuso,
scadenze, tempo residuo, volatilità, tassi, dividendi, moltiplicatore del
contratto, open interest e convenzione dei segni call/put. Non importare
implicitamente convenzioni o risultati Serafini.

Eseguire i test del motore e una verifica riproducibile su una fotografia reale,
registrando identificativo non sensibile, impronta SHA-256 del file, parametri,
risultati e confronto con un riferimento Edge calcolato indipendentemente.
Distinguere test sintetici, verifica su dati reali e lettura del bucket.

## Streamlit Community Cloud

Dopo il recupero e la verifica del codice:

1. Identificare l'entrypoint Streamlit reale e fissare dipendenze e versione
   Python compatibili; non inventare un percorso applicativo prima del recupero.
2. Installare le dipendenze in un ambiente isolato, eseguire i test e avviare
   l'app in locale. Verificare anche il caricamento della fotografia e il
   risultato del motore: un endpoint di salute non basta.
3. Caricare nel solo repository Edge il codice verificato, senza segreti e senza
   dati privati. Controllare il diff prima del push; non usare force push.
4. Nell'account Streamlit del proprietario creare una nuova applicazione dal
   repository `GrespoSan/SPX-Edge-GEX-Lab`, branch `main`, selezionando
   l'entrypoint verificato. Non modificare eventuali app Serafini.
5. Impostare la versione Python verificata, la visibilità appropriata e i soli
   segreti di lettura necessari. Le impostazioni segrete locali di Codex non
   vengono trasferite automaticamente a Streamlit.
6. Avviare il deploy e controllare i log evitando di esporre credenziali.
7. Verificare l'URL assegnato realmente dalla piattaforma: apertura dell'app,
   accesso autorizzato, caricamento della fotografia e calcolo Edge. Se l'app
   richiede autenticazione, completare anche la verifica autenticata.

Non dichiarare l'app pubblicata finché l'URL online non è stato verificato.
Registrare separatamente commit distribuito, URL, esito dei test, verifica
dell'accesso in sola lettura e limiti ancora presenti.
