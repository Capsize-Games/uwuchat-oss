# Legitimate Interest Assessment (LIA) — Email Integration Data

**Controller:** Capsize LLC (UwUchat)
**Date of assessment:** 2026-07-15
**Status:** Internal compliance record — not user-facing.
**Review note:** Produced by engineering; not a substitute for legal counsel
review.  Should be reviewed by an actual lawyer before scaling to
meaningfully more EU users or before any enforcement inquiry.

---

## 1. Purpose test

### What feature does this serve?

UwUchat offers an optional email integration (Fastmail / JMAP) that lets the
account holder connect their email account so the AI assistant can:

- Search and summarise email threads on the user's behalf
- Surface relevant email context during conversations
- Build a contact graph and entity knowledge base from the user's own inbox
  (relationship facts, co-occurrence patterns, derived knowledge facts)

### Why does it need correspondent data specifically?

The feature necessarily processes email messages **sent by and addressed to**
people who are not UwUchat users (the account holder's correspondents).
Without access to sender/recipient names, addresses, and message content, no
meaningful email search, summarisation, or contact insight can be produced.

The data is used **solely** to deliver the feature the account holder
requested.  It is never repurposed for marketing, model training, or building
profiles of non-users beyond what the feature requires.

---

## 2. Necessity test

### Minimum data needed

| Data category | Why it is necessary |
|---|---|
| Sender / recipient name and email address | Identify who the account holder is communicating with; build contact records |
| Message subject and body | Search, summarise, and extract facts the user asks about |
| Thread metadata (dates, thread IDs) | Organise and deduplicate threads |
| Derived contact relationship notes | Surface "who knows whom" context for the user |
| Derived knowledge facts (data_source="email") | Answer factual questions the user asks about their email history |

### How the PII masking pipeline reduces necessity further

When the PII masking pipeline (Phases 1/3/4 of
`plans/uwuchat-pii-masking-before-llm.md`) is enabled:

- Raw email content containing correspondent PII **never leaves the server**
  in its original form when sent to the third-party LLM provider.
- The LLM sees only masked placeholders (e.g. `[PERSON_1]`,
  `[EMAIL_ADDRESS_1]`).
- Original values are restored server-side before results are shown to the
  account holder.
- This means the LLM provider processes **de-identified** text for email
  content, reducing the necessity of exposing raw correspondent PII at the
  sub-processor level.

---

## 3. Balancing test

### Correspondents' reasonable expectations

People who email an UwUchat user generally expect that the recipient's own
tools (email client, search, assistant software) will process the message.
This is consistent with how webmail, CRM, and email-assistant products
operate industry-wide.

Reasonable expectations are **not** that:

- The recipient's AI assistant will share their data with unrelated third
  parties for marketing or advertising.
- Their data will be used to train AI models.
- Their data will be retained indefinitely after the account holder stops
  using the service.

### Account holder's interest

The account holder has a legitimate interest in using AI tools to manage
their own inbox — searching, summarising, and recalling information from
communications they have already received.  This is the core value
proposition of an AI-powered email assistant.

### Mitigations that tip the balance

| Mitigation | How it protects correspondents |
|---|---|
| Legitimate-interest-only use | Data is never sold, never used for marketing, never used for model training |
| PII masking before LLM egress | Correspondent names, emails, and other identifiers are replaced with placeholders before reaching the third-party LLM provider |
| Erasure channel for correspondents | Non-users can contact **contact@uwuchat.com** to request deletion of data about them; documented in the Privacy Policy |
| Account-holder-controlled integration | The feature is opt-in; the account holder must explicitly connect an email account |
| Retention tied to account holder | Ingested email data is purged within 30 days of account deletion or email disconnection |

---

## 4. Outcome

Processing of correspondent personal data via the UwUchat email integration
is justified under **Art. 6(1)(f) GDPR (legitimate interests)** subject to
the mitigations listed above, particularly:

1. PII masking before third-party LLM egress (when enabled), and
2. The correspondent erasure channel documented in the Privacy Policy.

The balancing test is favourable to the controller because:

- The processing is limited to what the account holder requested.
- Mitigations substantially reduce the privacy impact on correspondents.
- Correspondents have a clear path to exercise their rights.
- The controller does not repurpose the data for any secondary use.

This assessment should be re-visited if:

- The email feature is extended to process data for purposes beyond what the
  account holder requested (e.g. analytics, product improvement on
  correspondent data).
- The user base grows to a scale where manual correspondent erasure requests
  become operationally impractical (a self-serve flow should be built before
  that point).
- A DPA with OpenRouter is not confirmed to extend explicitly to
  email-derived content (not only chat messages).
