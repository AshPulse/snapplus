# Snap+ — Avvio locale

Struttura del progetto:
```
snapplus/
├── backend/     (FastAPI + Discord bot)
│   ├── server.py
│   ├── bot.py
│   ├── requirements.txt
│   └── .env
└── frontend/    (React)
    ├── src/
    ├── package.json
    └── .env
```

## Opzione A — Script automatico (Linux/Mac)
Dalla cartella `snapplus/`:
```bash
./start.sh
```
Fa tutto: venv, dipendenze, avvia backend (porta 8000) e frontend (porta 3000).

## Opzione B — Manuale, due terminali

### Terminale 1 — Backend
```bash
cd snapplus/backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 -m uvicorn server:app --reload --port 8000
```

### Terminale 2 — Frontend
```bash
cd snapplus/frontend
npm install --legacy-peer-deps
npm start
```

Poi apri: http://localhost:3000

## Note importanti
- **MongoDB**: il backend prova a connettersi a `mongodb://localhost:27017`.
  Senza Mongo l'API parte ma registrazioni/login non salvano. Per installarlo:
  `sudo apt install mongodb` oppure usa MongoDB Atlas e cambia `MONGO_URL` in `backend/.env`.
- **NumVerify**: la chiave è già in `backend/.env` (`NUMVERIFY_API_KEY`).
  Senza chiamate disponibili, il sito valida comunque in locale sulla lunghezza del numero.
- **Discord bot**: si configura dall'admin panel (token, canali). 
  Per il comando `!timer` serve attivare *Server Members Intent* (e per il prefisso anche *Message Content Intent*) nel Developer Portal. In alternativa usa `/timer`.
- **Frontend .env**: `REACT_APP_BACKEND_URL=http://localhost:8000`. 
  In produzione metti l'URL pubblico del backend.

## Cosa è stato aggiunto in questa versione
1. **NumVerify** — validazione numero in tempo reale + selettore paese (FR/IT/DE/ES/GB/BE) nella pagina di registrazione.
2. **Flusso OTP con 3 bottoni** nel DM Discord dell'admin: ❌ Decline (con modal commento), 🔄 Retry (nuovo codice), ✅ Success.
   Nuovi stati utente: `code_received`, `declined`.
3. **Comando timer** — `!timer @utente 24h [@Ruolo]` (o `/timer`): assegna un ruolo a tempo, aggiorna il messaggio con il tempo rimanente e rimuove il ruolo alla scadenza.
4. **Sicurezza** — rate limiting (register/validate/submit), header di sicurezza aggiuntivi (HSTS, COOP), rimozione header `Server`.
