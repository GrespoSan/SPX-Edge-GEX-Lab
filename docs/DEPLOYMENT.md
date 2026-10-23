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

## Lettura automatica del bucket privato

Seguire la procedura aggiornata in [AUTOMATIC_ACCESS.md](AUTOMATIC_ACCESS.md).
La nuova interfaccia richiede il login dell'utenza dedicata prima di accedere
ai dati privati. Configurare soltanto URL, chiave publishable/anon, User UID e
flag di attivazione nei Secrets della sola Edge; niente password Auth, JWT
condivisi, service-role key o URL firmati globali.

Il bucket resta privato. Storage riceve solo richieste di elenco e download;
le POST Auth servono al login e rinnovo della sessione, non a scrivere fotografie.
La policy dedicata e' una SELECT per un solo UID e per i soli percorsi raw SPX;
va installata e verificata prima di attivare il collegamento.
Il caricamento locale e il demo restano utilizzabili senza queste impostazioni.

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
