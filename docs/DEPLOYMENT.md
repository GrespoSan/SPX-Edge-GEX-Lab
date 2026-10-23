# Pubblicazione indipendente su Streamlit Community Cloud

## Configurazione della nuova app

Usare **Create app** nell'account Streamlit del proprietario e collegare soltanto:

| Campo | Valore |
| --- | --- |
| Repository | `GrespoSan/SPX-Edge-GEX-Lab` |
| Branch | `main` |
| Main file path | `edge_streamlit.py` |
| Python | `3.12` nelle impostazioni avanzate |
| Dipendenze | `requirements.txt`, con `constraints.txt` |
| Visibilità | Solo utenti autorizzati a vedere i dati privati |

Non modificare eventuali app Serafini. Non configurare cron-job, callback, MT4,
feed CBOE live o connessioni ai suoi database. Non servono Node.js, Alpaca,
FastAPI, una base dati o una service-role key per l'app Streamlit.
L'app parte senza Secrets; il caricamento manuale e l'esempio sintetico restano
disponibili anche senza Supabase.

## Lettura del bucket privato

Il bucket `spx-snapshots` non deve essere reso pubblico. Non creare o modificare
policy, ruoli, utenti, funzioni o oggetti nel progetto Supabase esistente.
Usare soltanto un accesso compatibile già autorizzato dal proprietario.
Il modulo `edge_storage.py` usa esclusivamente GET di un singolo oggetto,
con TLS verificato, senza redirect, senza elenchi o generazione di URL firmati.

Scegliere **una** delle seguenti configurazioni nel pannello Secrets della
**nuova app Streamlit**, senza inserire valori nel repository o in chat.

### URL firmato già disponibile

Impostare `SUPABASE_SNAPSHOT_SIGNED_URL` con un URL già emesso, limitato a una
fotografia specifica sotto `/storage/v1/object/sign/spx-snapshots/`.
Il dominio deve appartenere a un progetto `*.supabase.co`.
Se `SUPABASE_URL` è configurato, il dominio deve corrispondere a quel progetto.
Selezionare «Fotografia con URL firmato» nell'app e premere «Leggi fotografia».
L'app non riceve né usa la chiave amministrativa necessaria per emettere URL.
La scadenza del link deve essere gestita fuori dall'app da un soggetto già
abilitato; Edge non rinnova o crea firme. L'intero URL è un segreto.

### Identità già limitata alla lettura

Impostare:

| Secret | Significato |
| --- | --- |
| `SUPABASE_URL` | URL HTTPS del progetto esistente |
| `SUPABASE_ANON_KEY` | Chiave publishable/anon del progetto, mai una chiave privilegiata |
| `SUPABASE_READ_TOKEN` | JWT di un'identità esistente, con privilegi limitati alla lettura degli oggetti necessari |
| `SUPABASE_READ_ONLY_CONFIRMED` | `true` solo dopo la verifica dei privilegi esistenti da parte del proprietario |

Selezionare «Oggetto Supabase privato», indicare il percorso completo relativo al
bucket e premere «Leggi fotografia». Non inserire il nome del bucket nel percorso.
Una chiave publishable/anon da sola **non prova** l'accesso al bucket privato.
La conferma non restringe i privilegi: registra una verifica già svolta.
L'esito positivo di un GET non dimostra che l'identità sia di sola lettura.
Non provare upload o cancellazioni per controllarlo.

L'app rifiuta chiavi `sb_secret_*` e JWT con ruoli privilegiati noti prima di
eseguire richieste. Questa esclusione locale non sostituisce il controllo RLS
del proprietario; il server Supabase verifica l'autenticità del JWT.
Non configurare service-role key, credenziali del database o account amministrativi.
Se non esiste un accesso compatibile, fermare questa integrazione e usare
il caricamento manuale; eventuali modifiche Supabase non rientrano nel mandato.

## Segreti, dati e sessioni

Il modello `.streamlit/secrets.toml.example` contiene solo commenti e placeholder.
In locale, `.streamlit/secrets.toml`, `.env` e `local-data/` sono esclusi da Git.
La pubblicazione Codex non trasferisce automaticamente i Secrets a Streamlit.
Le fotografie non sono conservate in cache condivise: solo nella sessione che
le ha lette. Cambiare sorgente, percorso o credenziali elimina la lettura precedente.
Errori HTTP e di connessione non mostrano URL firmati, token o risposte remote.
Il download remoto è limitato a 25 MiB; il JSON decompresso a 100 MiB.
La visibilità dell'app va verificata prima di abilitare dati privati.

## Verifica prima e dopo il deploy

1. Installare `requirements-dev.txt`; eseguire `python -m pytest tests -q`.
2. Verificare il caricamento e il calcolo locale su una fotografia reale
   autorizzata. Usare `scripts/verify_snapshot.py`, annotando hash, timestamp,
   scadenze e risultati; non commettere dati privati o report sensibili.
3. Confermare che l'identità sia già di sola lettura, senza cambiare Supabase.
4. Eseguire il deploy della nuova app e controllare eventuali errori nei log.
5. Aprire l'URL **assegnato realmente da Streamlit** con l'identità prevista.
6. Controllare accesso, caricamento di una fotografia e risultati del motore;
   lo stato HTTP o un endpoint di salute, da soli, non dimostrano il funzionamento.
7. Registrare commit distribuito, URL, data della prova ed esito del controllo.

Non dichiarare l'app pubblicata finché il suo URL non è stato verificato.
Un deploy Codex dell'ambiente di sviluppo è distinto dal deploy Streamlit.
Non esiste al momento un URL Streamlit verificato in questa sessione.
