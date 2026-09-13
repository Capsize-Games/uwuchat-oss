/**
 * UwUchat — Privacy Policy page (/privacy).
 * Last updated: 2026-06-15
 */

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { PublicShell } from "../layout/PublicShell";

const EFFECTIVE_DATE = "June 17, 2026";

const PRIVACY_CONTENT = `
# Privacy Policy

**Effective date:** ${EFFECTIVE_DATE}
**Last updated:** ${EFFECTIVE_DATE}

Capsize LLC ("we," "us," or "our") operates UwUchat. This Privacy Policy
explains what personal data we collect, how we use it, and your rights
regarding that data. It applies to all users of uwuchat.com and the UwUchat
service.

---

## 1. Data We Collect

### Account Information
- Email address
- Username
- Password (stored as a cryptographic hash — we never store your plain-text
  password)
- Sign-up agreement records: whether and when you agreed to our Terms,
  confirmed you are 18+, and confirmed entertainment-only use; the IP address
  at the time of agreement (audit trail for GDPR Article 7 compliance)

### Payment Information
Payment is processed by our third-party payment processor. We do not store
full card numbers or CVV codes. We receive a tokenized reference and the last
four digits of your card for receipts.

### Usage and Technical Data
- IP address and approximate geolocation (country / region)
- Browser type and version, device type, operating system
- Pages visited, features used, timestamps of activity (usage logs)
- Error logs (for debugging — do not contain message content)

### Character and Chat Data
- The characters you create (name, description, personality settings)
- Your chat history with AI characters

### Email Integration Data
If you connect an email account (Fastmail / JMAP), we ingest and process:

- Sender and recipient names and email addresses
- Message content (bodies and attachments)
- Derived contact records and relationship facts (entity knowledge graph)
- Thread summaries and extracted knowledge facts

This necessarily includes personal data of people who are **not** UwUchat
users — your email correspondents.  Their data is processed under legitimate
interest (Art. 6(1)(f) GDPR) solely to provide the connected-account feature
you requested.  It is never sold, never used to build profiles of non-users
for any purpose beyond the feature, and never used for marketing or model
training.  Correspondents may request erasure of data about them by contacting
**contact@uwuchat.com**.

### What We Do NOT Collect
- We do not use the **content** of your conversations to train AI models without
  your explicit, separately obtained consent.
- We do not sell personal data to third parties.
- We do not use personal data for targeted advertising.

---

## 2. How We Use Your Data

| Purpose | Lawful basis (GDPR) |
|---|---|
| Account authentication and security | Contract / Legitimate interest |
| Delivering the UwUchat service | Contract |
| Processing payments | Contract |
| Sending service emails (verification, receipts) | Contract |
| Safety: detecting prohibited content and abuse | Legal obligation / Legitimate interest |
| Product improvement and debugging (aggregated/anonymized) | Legitimate interest |
| Responding to legal requests | Legal obligation |
| Audit trail for ToS agreement | Legal obligation (GDPR Art. 7) |

---

## 3. Data Retention

| Data type | Retention period |
|---|---|
| Account and profile data | Until you delete your account, then purged within 30 days |
| Chat history | Until you delete your account or request deletion |
| Ingested email content, contact records, and entity graph data | Until you delete your account or disconnect the email integration, then purged within 30 days |
| Payment records | 7 years (legal / tax requirement) |
| Usage and access logs | 90 days rolling |
| Security / abuse logs | Up to 1 year |

---

## 4. Data Sharing and Third Parties

We share data with the following categories of third parties only as necessary
to operate the service:

- **AI inference providers** (e.g., OpenRouter): Your messages are transmitted
  to inference endpoints to generate responses. These providers process data
  subject to their own privacy policies and data processing agreements with us.
  Message content is not retained by providers beyond the scope of processing
  the inference request.
- **Payment processor** (e.g., Stripe): Processes billing securely. Subject to
  PCI-DSS compliance and their privacy policy.
- **Hosting and infrastructure** (e.g., Cloudflare, cloud hosting provider):
  Servers that store and process your data, subject to appropriate data
  processing agreements.
- **Law enforcement**: When legally required (court order, subpoena, or legal
  obligation).

We do not share personal data with data brokers, advertisers, or any party for
commercial purposes unrelated to delivering the service.

**Correspondent data**: Data about people who are not UwUchat users (e.g. your
email correspondents) is processed under legitimate interest solely to provide
the connected-account feature you requested.  It is never sold, never used to
build profiles of non-users beyond that purpose, and never used for marketing
or training AI models.  Correspondents may request access to or erasure of data
about them by contacting **contact@uwuchat.com** — see Section 6 (Your
Rights) for details.

---

## 5. Cookies and Analytics

We use minimal, privacy-respecting analytics to understand aggregate usage
patterns (e.g., feature adoption, error rates). We do not use third-party
advertising cookies. A cookie consent notice will be shown to EU/UK users
where required.

Essential session cookies are required for the service to function and cannot
be opted out of while using UwUchat.

---

## 6. Your Rights

### All Users
- **Access**: Request a copy of the personal data we hold about you.
- **Correction**: Ask us to correct inaccurate data.
- **Deletion ("Right to be Forgotten")**: Request deletion of your account and
  associated data. You can do this yourself at any time from your account
  settings or by emailing contact@uwuchat.com.
- **Data Portability**: Request an export of your data in a machine-readable
  format by emailing contact@uwuchat.com; response within 30 days.
- **Withdraw Consent**: Where processing is based on consent, you may withdraw
  it at any time (this does not affect prior processing).

### EU / UK Users (GDPR / UK GDPR)
In addition to the above, you have the right to:
- **Object** to processing based on legitimate interests.
- **Restrict** processing in certain circumstances.
- Lodge a complaint with your **supervisory authority** (e.g., your country's
  data protection authority, or the ICO in the UK).

### Colorado Residents (Colorado Privacy Act, C.R.S. § 6-1-1301)
You have the right to:
- Opt out of the sale or sharing of your personal data (we do not sell data).
- Opt out of profiling in furtherance of automated decisions producing legal or
  similarly significant effects (we do not engage in such profiling).
- Access, correct, delete, and obtain a portable copy of your data.

To exercise any right, contact us at **contact@uwuchat.com** or use the
[Data Request](/data-request) page. We will respond within **30 days** (GDPR
Article 12 deadline). We may ask you to verify your identity before fulfilling
a request.

---

## 7. Security

We use industry-standard security measures including:
- Passwords hashed with Argon2id (OWASP-recommended)
- TLS encryption in transit
- Encryption at rest for conversation content and memory summaries
- Uploaded knowledge-base documents are stored unencrypted to support search
- JWT access tokens with short expiry (15 minutes) and refresh token rotation

No system is perfectly secure. Please notify us at contact@uwuchat.com if you
discover a vulnerability.

---

## 8. Children's Privacy

UwUchat is not directed at individuals under 18. We do not knowingly collect
personal data from anyone under 18. If you believe we have inadvertently
collected such data, contact us immediately at contact@uwuchat.com and we will
delete it promptly.

---

## 9. International Transfers

Your data is stored on servers located in the United States. If you access
UwUchat from the EU, UK, or other jurisdictions with data transfer
restrictions, please note that we transfer data to the US under appropriate
safeguards (Standard Contractual Clauses where applicable).

---

## 10. Changes to This Policy

We may update this Privacy Policy from time to time. Material changes will be
communicated by email or by a prominent in-app notice at least 30 days before
they take effect. Continued use after the effective date constitutes acceptance
of the updated policy.

---

## 11. Contact / Data Protection

For privacy questions, data requests, or to exercise your rights:

**Contact:** contact@uwuchat.com

**Capsize LLC**
Colorado, United States

---

*Last updated: ${EFFECTIVE_DATE}.*
`;

export default function PrivacyPolicy() {
  return (
    <PublicShell>
      <div className="legal-page">
        <div className="legal-container">
          <div className="legal-content">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{PRIVACY_CONTENT}</ReactMarkdown>
          </div>
        </div>
      </div>
    </PublicShell>
  );
}
