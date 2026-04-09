# ADS System & Home Lab Monitor Bot

Telegram bot per monitorare una Raspberry Pi o un piccolo home lab.

Il bot permette di:
- vedere lo stato della macchina locale
- controllare gli host configurati in rete
- limitare l’accesso ai soli utenti autorizzati
- ricevere una notifica quando l’uptime raggiunge 30 giorni

---

## Funzionalità

Comandi disponibili:

- `/start` — mostra i comandi disponibili
- `/status` — mostra lo stato della macchina locale
- `/hosts` — mostra l’elenco degli host monitorati
- `/pingall` — esegue il ping di tutti gli host configurati
- `/chatid` — mostra `user_id` e `chat_id`

Informazioni mostrate da `/status`:
- hostname
- sistema operativo e kernel
- uptime
- utilizzo CPU
- load average
- RAM usata/totale
- spazio disco
- temperatura CPU
- stato alimentazione Raspberry tramite `vcgencmd get_throttled`

Funzioni aggiuntive:
- accesso consentito solo agli utenti autorizzati
- notifica automatica quando l’uptime raggiunge 30 giorni

---

## Struttura del progetto

```text
ADS_system_lab_monitor_bot/
├── ADS_system_lab_monitor_bot.py
├── config.example.json
├── .gitignore
├── requirements.txt
├── lab_monitor_bot.service
└── README.md