/**
 * Diagramas mermaid de la arquitectura de pulpo.
 * Mantenerlos sincronizados a mano con la estructura real — no se generan
 * dinámicamente. Revisar cuando se mueven/renombran módulos (ver CLAUDE.md).
 * Espejo en docs/adr/007-diagramas-arquitectura.md para que también se vea
 * en git/GitHub sin depender de la UI.
 */

export const LAYERS_DIAGRAM = `
graph TD
  subgraph Interfaces["interfaces/ — solo coordinan, sin lógica propia"]
    API["api/ — FastAPI puro, routers bajo /api"]
    UI["ui/ — API + SPA estática (prod)"]
    CLI["cli/ — pulpo server ui|api"]
    LIB["lib/ — PulpoClient in-process"]
  end

  subgraph Domain["business/ + graphs/ — TODA la lógica vive acá"]
    BOTS_SVC["business/bots.py"]
    FLOWS_SVC["business/flows.py"]
    CONN_PHONES["business/connections_phones.py<br/>(WhatsApp · connections.json)"]
    CONN_GOOGLE["business/connections_google.py<br/>(Google service accounts · DB)"]
    COMPILER["graphs/compiler.py<br/>ejecuta flows nodo por nodo"]
    NODES["graphs/nodes/*.py<br/>un archivo por tipo de nodo"]
  end

  subgraph External["tools/ + bots/ — todo lo externo que un nodo usa"]
    WAVI["tools/wavi_driver.py<br/>WhatsApp"]
    TELEGRAM["bots/telegram_bot.py<br/>Telegram (polling)"]
    TRANSCRIBE["tools/transcription.py"]
  end

  CORE["core/ — db.py, config.py, state.py, lifespan.py"]

  API --> Domain
  UI --> Domain
  CLI --> Domain
  LIB --> Domain

  COMPILER --> NODES
  NODES -->|"import directo, nadie más"| External
  Domain --> CORE
  External --> CORE

  classDef iface fill:#1e3a5f,stroke:#3b82f6,color:#e2e8f0
  classDef domain fill:#1a2e1a,stroke:#22c55e,color:#e2e8f0
  classDef ext fill:#3a1e1e,stroke:#ef4444,color:#e2e8f0
  classDef core fill:#2e2e1a,stroke:#eab308,color:#e2e8f0
  class API,UI,CLI,LIB iface
  class BOTS_SVC,FLOWS_SVC,CONN_PHONES,CONN_GOOGLE,COMPILER,NODES domain
  class WAVI,TELEGRAM,TRANSCRIBE ext
  class CORE core
`.trim()

export const CONNECTIONS_DIAGRAM = `
graph LR
  subgraph Canales["Canales — llegan mensajes"]
    WA_USER["Usuario WhatsApp"]
    TG_USER["Usuario Telegram"]
  end

  WA_USER --> WAVI_DRIVER["tools/wavi_driver.py<br/>poller sobre CLI wavi"]
  TG_USER --> TG_BOT["bots/telegram_bot.py<br/>python-telegram-bot, polling"]

  WAVI_DRIVER --> RUN_FLOWS["graphs/compiler.py: run_flows()"]
  TG_BOT --> RUN_FLOWS

  RUN_FLOWS --> FLOW_DEF["flows (JSON en DB)<br/>nodos + edges, editados en el UI"]

  subgraph ConexionesConfig["Config de conexiones — dos modelos de persistencia distintos"]
    PHONES["business/connections_phones.py<br/>números WhatsApp por bot · sync sobre connections.json"]
    GOOGLE["business/connections_google.py<br/>service accounts por bot · async sobre DB"]
  end

  CONN_JSON[("connections.json")]
  DB[("SQLite · data/messages.db")]

  PHONES --> CONN_JSON
  GOOGLE --> DB
  FLOW_DEF -.usa credenciales.-> GOOGLE

  classDef canal fill:#1e3a5f,stroke:#3b82f6,color:#e2e8f0
  classDef conn fill:#1a2e1a,stroke:#22c55e,color:#e2e8f0
  classDef store fill:#2e2e1a,stroke:#eab308,color:#e2e8f0
  class WA_USER,TG_USER,WAVI_DRIVER,TG_BOT canal
  class PHONES,GOOGLE,RUN_FLOWS,FLOW_DEF conn
  class CONN_JSON,DB store
`.trim()
