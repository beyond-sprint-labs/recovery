# DueGuide
### Turn overdue into opportunity.

**AI-powered invoice recovery. Merchant-controlled decisions. PayPal-powered execution.**

An overdue invoice shouldn't automatically become a lost customer.

DueGuide reimagines invoice recovery by transforming payment difficulties into structured opportunities for resolution. Instead of relying on generic reminders or inflexible collection workflows, DueGuide combines conversational AI, deterministic financial calculations, merchant-defined policies, and PayPal's developer platform to support more intelligent repayment decisions.

Built by **Beyond Sprint Labs** for the PayPal Dev Hackathon 2026.

---

## The Problem

Traditional invoice recovery often treats every overdue payment the same way.

But customers face different circumstances. Some can make a partial payment immediately. Others need installments or a reasonable settlement.

Merchants need a way to evaluate these requests without sacrificing financial control, operational efficiency, or transparency.

**DueGuide bridges that gap.**

## How It Works

1. **Identify:** A merchant selects an overdue invoice.
2. **Understand:** Google Gemini interprets the customer's payment request.
3. **Calculate:** A deterministic financial engine evaluates settlement and installment alternatives.
4. **Protect:** Merchant-defined policies and validation guardrails prevent unauthorized financial terms.
5. **Approve:** The merchant selects and approves an eligible proposal.
6. **Execute:** Following customer acceptance, PayPal Sandbox supports the invoice replacement workflow.
7. **Track:** Payment events and proposal state transitions are recorded in an auditable workflow.

**AI assists. Financial rules constrain. Humans authorize. PayPal executes.**

## Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| Frontend | React, TypeScript, Vite | Merchant and customer interfaces |
| Audit interface | AG Grid Community | Transaction and decision visibility |
| Backend | Python, FastAPI | API orchestration and business logic |
| AI | Google Gemini API | Customer intent interpretation and structured negotiation |
| Financial engine | Python Decimal | Deterministic calculations and policy validation |
| Payments | PayPal Invoicing API v2 | Sandbox invoice lifecycle operations |
| Event synchronization | PayPal Webhooks | Payment-event processing and status updates |
| Persistence | SQLAlchemy, SQLite | Invoices, proposals, states, and audit records |
| Deployment | Oracle Cloud Infrastructure, Caddy, Uvicorn | Documented HTTPS deployment architecture |
| Quality assurance | Pytest, Ruff | Automated tests and code quality |

## PayPal Integration

DueGuide integrates the **PayPal Invoicing API v2** using the free PayPal Sandbox environment.

The integration supports invoice creation, sending and cancellation as part of the controlled renegotiation workflow.

After merchant approval and customer acceptance, the backend coordinates the supported invoice operations. Webhooks provide payment-related events that can update application state and the audit trail.

The system includes idempotency safeguards, lifecycle validation, and reconciliation handling to reduce the risk of duplicate or inconsistent operations.

**PayPal execution is never authorized solely by AI-generated text.**

## AI Integration

DueGuide uses **Google Gemini** to interpret natural-language payment requests and produce structured negotiation inputs.

The language model does not independently calculate payment schedules, override merchant policies, or initiate unauthorized PayPal operations.

A separate deterministic financial engine calculates monetary values using Python Decimal arithmetic. Validation layers enforce merchant-defined limits and reject invalid or unsupported proposals.

The project includes scenarios for policy violations, ambiguous requests, invalid model output, and adversarial instructions.

## AG Grid Integration

DueGuide uses **AG Grid Community** for its Live Audit Grid.

The interface is designed to make important events visible, including proposal creation, policy enforcement, approval decisions, invoice operations, and payment-related status changes.

The objective is straightforward: **make financial automation observable, not opaque.**

## Getting Started

### Requirements

- Python 3.12 or 3.13
- Git
- A Python virtual environment
- PayPal Sandbox credentials and a Gemini API key for real-provider integration

### Install the backend

```bash
git clone https://github.com/beyond-sprint-labs/recovery.git
cd recovery

python -m venv .venv
source .venv/bin/activate

pip install -e ".[dev]"
```

On Windows, activate the environment with:

```powershell
.venv\Scripts\Activate.ps1
```

### Configure the environment

Create a local `.env` file using `.env.example` as a reference.

For local simulated development, configure:

```dotenv
APP_ENV=local
DEMO_MODE=true
PAYPAL_MODE=mock
AGENT_MODE=scripted
DATABASE_URL=sqlite:///./recovery.db
PUBLIC_BASE_URL=http://localhost:8000
CORS_ORIGINS=http://localhost:5173
```

Run the API:

```bash
uvicorn app.main:app --reload
```

Verify the backend:

```text
http://localhost:8000/health
```

For real Gemini and PayPal Sandbox integration, configure the appropriate provider settings and credentials according to the deployment documentation.

**Never commit API keys, client secrets, private credentials, or a populated `.env` file.**

### Run automated tests

```bash
python -m pytest
ruff check .
ruff format --check .
```

### Frontend

The frontend is located in the `ui/` directory.

Install dependencies and start the development server:

```bash
cd ui
npm install
npm run dev
```

The frontend supports mock and backend-connected configurations. Consult its environment settings when switching to the real API.

## Deployment

The repository includes a deployment guide for Oracle Cloud Infrastructure.

**[Deployment instructions](docs/DEPLOY.md)**

The documented architecture uses Python, Uvicorn, SQLite, Caddy, and HTTPS. It also covers PayPal Sandbox configuration, webhook registration, and deployment verification.

## Technical Documentation

- [Financial engine and calculation rules](docs/FINANCE.md)
- [Demo seed data](docs/SEED.md)
- [OCI deployment guide](docs/DEPLOY.md)
- [Interface microcopy](docs/marketing/microcopy_en.md)

## Security and Responsible AI

DueGuide follows a controlled execution model:

- Merchant policies are enforced server-side.
- Financial calculations are deterministic and independently validated.
- AI-generated output is checked before downstream execution.
- Customer-facing views are separated from internal merchant information.
- Sensitive credentials remain outside source control.
- Audit records support traceability of financial decisions and state changes.

The system is a hackathon prototype operating with simulated data and PayPal Sandbox infrastructure, not a production financial service.

## Built by Beyond Sprint Labs

An international, multidisciplinary team combining software engineering, artificial intelligence, financial modeling, product management, quality assurance, and product design.

We believe the future of financial automation is not about removing human judgment.

**It's about giving people better information, safer options, and more control over what happens next.**

---

**DueGuide — Turn overdue into opportunity.**

*Developed for the PayPal Dev Hackathon 2026.*

## License

Licensed under the [MIT License](LICENSE).
