# Client-Side Caching Architecture

The React frontend implements a two-tier client-side cache using **`localStorage`** for small scalar data and **IndexedDB** (via [Dexie.js](https://dexie.org/)) for structured collections and binary assets. The design eliminates redundant server round-trips, enables instant-on rendering from cache, and keeps the app functional when the server is temporarily unreachable.

---

## Storage Tiers at a Glance

| Tier | Technology | What goes here |
|---|---|---|
| **localStorage** | `localStorage` API (synchronous) | UI preferences, auth prefs, sync timestamps, small scalars read on app boot |
| **IndexedDB** | Dexie.js (async, transactional) | Conversations, messages, LoRAs, embeddings, KB documents, CivitAI model details, thumbnails, canvas state, image dates |
| **Browser HTTP cache** | Native (no code required) | Generated image blobs served from server URLs |
| **Server only** | No local copy | Real-time model status, active download progress |

---

## Full Stack Overview

```mermaid
graph TD
    subgraph Client ["React Frontend (client/)"]
        direction TB
        Components["UI Components\n(panels, views)"]
        Hooks["Domain Hooks\nuseConversations · useLoras\nuseEmbeddings · useKnowledgeBaseDocs\nuseCivitaiDetailCache · useImageDates\n…"]
        LS["localStorage\n(sync-read on boot)"]
        IDB["IndexedDB\nDexie — airunner db\n(async, structured)"]
        SM["SyncManager\n(generic cache manager)"]
        WS["WebSocket Transport\nWsApiClient · event bus"]
    end

    subgraph Server ["Python Backend (FastAPI)"]
        API["REST + RPC Endpoints"]
        EventBus["Event Bus\nEVENT_LORAS · EVENT_IMAGES\nEVENT_CIVITAI_THUMBNAIL …"]
    end

    Components -->|"reads via"| Hooks
    Hooks -->|"serve immediately"| IDB
    Hooks -->|"read/write prefs"| LS
    Hooks -->|"manage"| SM
    SM -->|"delta-fetch"| WS
    SM -->|"bulkPut"| IDB
    WS <-->|"WebSocket frames"| API
    EventBus -->|"push events"| WS
    WS -->|"cache-invalidation signal"| Hooks
```

---

## The SyncManager Pattern

`SyncManager` (`client/src/db/SyncManager.ts`) is the generic cache-first fetch utility every domain hook builds on.

```mermaid
sequenceDiagram
    participant Hook as Domain Hook
    participant SM as SyncManager
    participant IDB as IndexedDB
    participant LS as localStorage
    participant Server

    Hook->>SM: readCached()
    SM->>IDB: table.toArray()
    IDB-->>SM: cached rows
    SM-->>Hook: cached rows (shown immediately)

    Hook->>SM: sync()
    SM->>LS: read airunner:sync:<table>
    LS-->>SM: lastSyncedAt (ISO string or null)
    SM->>Server: serverFetch(since?)
    Server-->>SM: fresh records
    SM->>IDB: bulkPut(fresh)
    SM->>LS: write airunner:sync:<table> = now()
    SM->>IDB: table.toArray()
    IDB-->>SM: merged result
    SM-->>Hook: merged result (re-renders)
```

### Constructor

```typescript
new SyncManager<T>(
  table:       Dexie.Table<T, unknown>,
  serverFetch: (since?: string) => Promise<T[]>,
  syncKey:     string,   // stored as airunner:sync:<syncKey> in localStorage
)
```

### Methods

| Method | Behaviour |
|---|---|
| `readCached()` | Returns all rows from the Dexie table immediately |
| `sync()` | Reads `lastSyncedAt` from localStorage, calls `serverFetch`, `bulkPut`s results, updates timestamp, returns merged table |
| `invalidate()` | Clears the table and removes the localStorage timestamp; next `sync()` does a full fetch |
| `getLastSynced()` | Returns the ISO timestamp string or null |
| `setLastSynced(ts)` | Writes directly (used internally after sync) |

> **Server compatibility:** `serverFetch` receives an optional `since` ISO timestamp. Servers that support `updated_after` filtering return only changed records (delta). Servers that ignore it return all records — `bulkPut` handles the merge safely either way.

---

## DbContext and the Null Fallback

`DbProvider` (`client/src/db/DbContext.tsx`) wraps the application and provides the Dexie instance via React context.

```mermaid
graph LR
    A["main.tsx\nDbProvider"] --> B["App.tsx"]
    B --> C["Domain Hooks\nuseDb()"]
    C -->|"db !== null"| D["IndexedDB path\n(normal)"]
    C -->|"db === null"| E["Server-direct path\n(private browsing / quota)"]
```

- In normal browsers the hook returns the `AiRunnerDb` Dexie instance.
- In Firefox private mode (and any context where `indexedDB.open()` throws), the hook returns `null`. Every domain hook checks for `null` and falls back to calling the server API directly — the app remains fully functional, just without a local cache.

---

## Conflict Resolution Strategies

Different data types require different merge behaviours when the client and server disagree.

| Data Type | Strategy | Rationale |
|---|---|---|
| Conversations (metadata) | **timestamp-wins** | `updatedAt` on each record; newer side overwrites |
| Messages | **append-only** | Messages are immutable once sent; `bulkPut` keyed by index merges without deleting |
| LoRAs / Embeddings | **timestamp-wins** | Server is authoritative; user edits (toggle, weight) are sent to server before cache is updated |
| KB Documents | **server-wins on toggle** | `toggleDocumentActive` is confirmed server-side; optimistic local update rolls back on error |
| CivitAI model details | **72 h TTL then server-wins** | CivitAI data changes rarely; server caches 72 h so client matches |
| CivitAI thumbnails | **cache-miss-only** | Thumbnails are immutable; once stored they are never overwritten |
| Canvas state | **`_ts` timestamp-wins** | `_ts` (monotonic `Date.now()`) is set on every mutation; higher value wins on load |
| Image dates | **server-wins** | Full replace on sync; stale dates pruned from IndexedDB |
| Settings singletons | **server-wins on mount** | Server value hydrates local state on every `SettingsView` open |

---

## Data Flow by Feature

### Chat History

```mermaid
sequenceDiagram
    participant P as ChatHistoryPanel
    participant H as useConversations
    participant IDB as IndexedDB
    participant API as /api/v1/llm/conversations

    P->>H: mount
    H->>IDB: readCached() → show immediately
    H->>API: listConversations(50)
    API-->>H: fresh list
    H->>IDB: bulkPut
    H-->>P: re-render with merged list

    P->>H: remove(id)
    H->>API: deleteConversation(id)
    H->>IDB: conversations.delete(id)
    H-->>P: re-render
```

### Conversation Messages (append-only)

```mermaid
sequenceDiagram
    participant V as ChatView
    participant H as useConversationMessages
    participant IDB as IndexedDB
    participant API as /api/v1/llm/conversations/select

    V->>H: load(conversationId)
    H->>IDB: messages.where(conversationId).sortBy(sortIndex)
    IDB-->>H: cached messages → render immediately
    H->>API: selectConversation(id)
    API-->>H: authoritative message list
    H->>IDB: bulkPut (keyed by conversationId_index)
    H-->>V: setMessages (full list)

    Note over V,H: New message sent
    V->>H: appendMessage(convId, msg, index)
    H-->>V: setMessages([...prev, msg])
    H->>IDB: messages.put(record)
```

### LoRAs / Embeddings

```mermaid
sequenceDiagram
    participant Panel as LoraPanel / EmbeddingsPanel
    participant H as useLoras / useEmbeddings
    participant IDB as IndexedDB
    participant Bus as Event Bus
    participant API as /api/v1/art/loras

    Panel->>H: mount
    H->>IDB: readCached() → render immediately
    H->>API: listLoras()
    API-->>H: fresh list
    H->>IDB: bulkPut
    H-->>Panel: merged list

    Bus-->>H: EVENT_LORAS {type:"reload"}
    H->>API: listLoras() (via sync())
    H->>IDB: bulkPut
    H-->>Panel: updated list

    Panel->>H: patchLora(updated)
    H-->>Panel: setLoras (optimistic)
    H->>IDB: loras.put(updated)
```

### Knowledge Base Documents

```mermaid
sequenceDiagram
    participant KB as KnowledgeBasePanel
    participant CV as ChatView
    participant H as useKnowledgeBaseDocs
    participant IDB as IndexedDB
    participant API as /api/v1/knowledge-base/documents

    Note over KB,CV: Both mount — single fetch
    KB->>H: mount
    CV->>H: mount
    H->>IDB: readCached()
    H->>API: listKnowledgeBaseDocuments()
    API-->>H: docs
    H->>IDB: bulkPut
    H-->>KB: docs
    H-->>CV: activeDocs (filtered)

    KB->>H: toggle(docId)
    H->>API: toggleDocumentActive(docId)
    API-->>H: {active: bool}
    H->>IDB: kbDocuments.put (updated)
    H-->>KB: re-render
    H-->>CV: re-render (active pill removed/added)
```

### CivitAI Browser

```mermaid
sequenceDiagram
    participant Panel as CivitaiBrowserPanel
    participant DC as useCivitaiDetailCache
    participant TC as useCivitaiThumbnailCache
    participant IDB as IndexedDB
    participant Bus as Event Bus
    participant API as CivitAI endpoints

    Panel->>DC: get(modelId)
    DC->>IDB: civitaiModels.get(modelId)
    IDB-->>DC: cached (if within 72h TTL)
    DC-->>Panel: cached data → show immediately

    alt cache miss or expired
        Panel->>API: fetchCivitaiModel(id)
        API-->>Panel: model data
        Panel->>DC: set(modelId, data)
        DC->>IDB: civitaiModels.put
    end

    Bus-->>Panel: EVENT_CIVITAI_THUMBNAIL\n{model_id, version_index, image_url, images_base64}
    Panel->>TC: store(modelId, vIdx, url, blob)
    TC->>IDB: civitaiThumbnails.get(key)
    IDB-->>TC: existing? skip (cache-miss-only)
    TC->>IDB: civitaiThumbnails.put (if new)
    Panel-->>Panel: setSelectedModelData (live update)
```

### Canvas State

```mermaid
sequenceDiagram
    participant CS as useCanvasState
    participant LS as localStorage
    participant IDB as IndexedDB
    participant Server as Canvas WebSocket

    Note over CS: Synchronous init (first render)
    CS->>LS: loadPersistedState()
    LS-->>CS: canvas state (instant)

    Note over CS: Async upgrade (after mount)
    CS->>IDB: loadPersistedStateAsync()
    IDB-->>CS: state with _ts
    CS->>CS: if IDB._ts > current._ts → setState(IDB state)

    Note over CS: On every mutation (300ms debounce)
    CS->>LS: localStorage.setItem (fallback sync)
    CS->>IDB: canvasDocuments.put {id:"default", documentJson, updatedAt:_ts}

    Note over CS: Server sync (WebSocket + HTTP PUT)
    CS->>Server: {document: JSON} on every change
    Server-->>CS: updated document on reconnect
    CS->>CS: loadFromJSON (timestamp-wins)
```

---

## localStorage Keys

All keys written by the caching layer follow the `airunner:` or `airunner_` prefix convention. Sync timestamps use `airunner:sync:<table>`.

### Sync Timestamps (written by SyncManager)

| Key | Meaning |
|---|---|
| `airunner:sync:conversations` | ISO timestamp of last conversation list sync |
| `airunner:sync:loras` | ISO timestamp of last LoRA list sync |
| `airunner:sync:embeddings` | ISO timestamp of last embeddings sync |
| `airunner:sync:kbDocuments` | ISO timestamp of last KB document sync |
| `airunner:sync:imageDates` | ISO timestamp of last image date list sync |

### Layout & UI State (written by `useLayoutPrefs`)

| Key | Type | Default |
|---|---|---|
| `airunner_show_chat` | boolean | `true` |
| `airunner_show_canvas` | boolean | `false` |
| `airunner_tts_on` | boolean | `false` |
| `airunner_stt_on` | boolean | `false` |
| `airunner_left_panel` | `PanelId \| null` | `null` |
| `airunner_right_panel` | `PanelId \| null` | `null` |
| `airunner_conversation_id` | `number \| null` | `null` |

### LLM / TTS / STT Settings (written by `useLlmPrefs`)

| Key | Type | Default |
|---|---|---|
| `airunner:modelPath` | string | `""` |
| `airunner:temperature` | number | `0.7` |
| `airunner:maxTokens` | `number \| null` | `null` |
| `airunner:selectedVoice` | string | `""` |
| `airunner:whisperModel` | string | `""` |
| `airunner:activeTab` | string | `"llm"` |

### Art & CivitAI Prefs (written by `useArtPrefs` / `useCivitaiPrefs`)

| Key | Type | Default |
|---|---|---|
| `airunner_art_model` | string | `""` |
| `airunner_art_version` | string | `""` |
| `airunner_seed` | string | `""` |
| `airunner_civitai_base_model` | string | `""` |
| `airunner_civitai_model_type` | string | `""` |
| `airunner_civitai_selected_model` | `number \| null` | `null` |
| `airunner_civitai_api_key` | string | `""` |

### Image Browser

| Key | Type |
|---|---|
| `airunner_image_browser_date` | `string \| null` |

---

## Storage Quota and Eviction

IndexedDB storage is finite. When a write throws `DOMException: QuotaExceededError`, the eviction policy in `client/src/db/evict.ts` kicks in:

```mermaid
graph TD
    W["write to IndexedDB"]
    W -->|"success"| Done["done"]
    W -->|"QuotaExceededError"| E1["evict 30 oldest civitaiThumbnails"]
    E1 -->|"retry write"| R1{"success?"}
    R1 -->|"yes"| Done
    R1 -->|"no"| E2["evict 30 oldest civitaiModels"]
    E2 -->|"retry write"| R2{"success?"}
    R2 -->|"yes"| Done
    R2 -->|"no"| E3["evict images → imageDates → loras → embeddings"]
    E3 --> Done
```

**Protected tables** (never evicted): `conversations`, `messages`, `canvasDocuments`, `kbDocuments`.

### Manual Cache Clear

```typescript
import { clearAllCache } from "client/src/db/evict";

await clearAllCache();
// Clears: civitaiThumbnails, civitaiModels, images, imageDates,
//         loras, embeddings, kbDocuments
// Removes: all airunner:sync:* localStorage keys
// Preserves: conversations, messages, canvasDocuments
```

---

## Developer Cache Debug Panel

In development mode (`npm run dev`) or when `?debug` is appended to any URL, a floating overlay appears in the bottom-right corner of the app.

The panel shows:
- Row count per IndexedDB table
- Last-sync timestamp per table
- **Force Sync** — clears `airunner:sync:<table>` so the next hook mount does a full re-fetch
- **Clear All** — calls `clearAllCache()` and refreshes the display
- **Refresh** — re-reads all counts without clearing

```
┌────────────────────────────────────────── Cache Debug ──── [Refresh] [Clear All] ─┐
│ Table                │ Rows │ Last Synced          │                               │
│ conversations        │   12 │ 14:32:01             │ [Force Sync]                  │
│ messages             │  204 │ (append-only)        │                               │
│ loras                │   47 │ 14:31:58             │ [Force Sync]                  │
│ embeddings           │   23 │ 14:31:59             │ [Force Sync]                  │
│ kbDocuments          │    5 │ 14:32:00             │ [Force Sync]                  │
│ civitaiModels        │    8 │ (TTL-based)          │                               │
│ civitaiThumbnails    │  312 │ (cache-miss-only)    │                               │
│ canvasDocuments      │    1 │ (timestamp-wins)     │                               │
│ imageDates           │    7 │ 14:31:57             │ [Force Sync]                  │
│ images               │   60 │ (by date)            │                               │
└───────────────────────────────────────────────────────────────────────────────────┘
```

---

## Adding a New Cached Data Type

Follow this checklist when caching a new server resource:

1. **Add a Dexie table** in `client/src/db/db.ts`:
   - Define the interface (extend it with `cachedAt: number`)
   - Add the table declaration and `version(1).stores()` entry with appropriate indexes
   - Bump the Dexie version number if changing an existing schema

2. **Write a domain hook** in `client/src/hooks/use<Name>.ts`:
   ```typescript
   export function useMyData() {
     const db = useDb();
     const [data, setData] = useState([]);

     const serverFetch = useCallback(async () => { /* call API */ }, []);

     const sync = useCallback(async () => {
       if (!db) { /* fallback */ return; }
       const manager = new SyncManager(db.myTable, serverFetch, "myTable");
       const cached = await manager.readCached();
       if (cached.length > 0) setData(cached);
       const merged = await manager.sync();
       setData(merged);
     }, [db, serverFetch]);

     useEffect(() => { sync(); }, [sync]);
     return { data, sync };
   }
   ```

3. **Add a sync key** to the `SYNC_TABLE_MAP` in `CacheDebugPanel.tsx`.

4. **Add the table** to the eviction order in `evict.ts` if it holds large data.

5. **Update `Home.md`** if the new data type warrants its own wiki page.
