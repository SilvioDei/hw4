# Campus Customs: shop + "Ask the Clerk" chatbot (HW 4)

This is a campus merch storefront with a React + Vite + TypeScript frontend and a Python FastAPI backend. The chatbot is a **PydanticAI agent** that reads price and stock only from the local SQLite database; it never guesses them.

Shoppers can:
- browse and filter products
- create an account and log in
- chat about merch, and see matching items appear on the page as product cards
- get similar in-stock suggestions when a size is sold out

Every price and stock number in a chat reply is fact-checked against the database.

## Repository layout

```
hw4/
├── AI_prompts.md              # log of the prompts used to build this
├── requirements.txt           # backend Python packages
├── .env.example               # copy to .env and add your key
├── .gitignore
├── README.md
├── frontend/                  # Vite React TypeScript app
├── backend/
│   ├── main.py                # FastAPI app: run with uvicorn main:app --reload --port 8000
│   ├── agent.py               # the agent: model, prompt, limits, fact-check, audit trail
│   ├── models.py              # Pydantic / PydanticAI types
│   ├── tools.py               # read-only database tools
│   └── prompts/
│       └── prompt.md          # system prompt: voice + safety rules
└── output/
    ├── harness.md             # how the system works: data, tools, models, safety, specs
    ├── design.md              # visual design notes
    ├── usability.md           # the four usability improvements + how to test them
    ├── app_check.html         # screenshot test report (double-click to open)
    ├── app_check_images/      # screenshots linked from app_check.html
    └── audit_trail.json       # append-only log of agent activity (no personal data)
```

The agent itself is four files: `backend/prompts/prompt.md`, `backend/agent.py`, `backend/tools.py`, and `backend/models.py`.

## 1. Place the data pack (not in git)

The database and product images are **not** in this repo. Put the course data pack inside `hw4/` so it looks like this:

```
hw4/
└── data/
    ├── campus_customs.db
    └── products/          # images referenced by the catalogue
```

If you have `data.zip`, unzip it into `hw4/`; it already contains the `data/` folder. The backend finds `data/` relative to `backend/`, so no paths need editing.

When a user signs up for the first time, the backend makes a backup at `data/campus_customs.backup.db`. That file is git-ignored too.

## 2. Requirements

- **Python 3.12+**
- **Node.js 20+** and npm
- A **Portkey API key** for OpenAI access. The model is `gpt-5.6-luna`; change `MODEL_NAME` in `backend/agent.py` to use another 5.6/6-series model.

## 3. One-time setup

Run these from the `hw4` folder. The commands are for Windows PowerShell; on macOS/Linux, use `source .venv/bin/activate` and `cp` instead of `copy`.

```powershell
# Backend: virtual environment + packages
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Your key: copy the template, then edit .env and paste your real key
copy .env.example .env

# Frontend packages
cd frontend
npm install
cd ..
```

`.env` should contain one line, `PORTKEY_API_KEY=<your key>`. It is git-ignored; never commit it.

## 4. Run it

Use **two terminals**. Start the backend first.

**Terminal 1: backend** (http://localhost:8000; API docs at http://localhost:8000/docs)

```powershell
cd backend
..\.venv\Scripts\Activate.ps1
uvicorn main:app --reload --port 8000
```

**Terminal 2: frontend** (http://localhost:5173)

```powershell
cd frontend
npm run dev
```

Then open **http://localhost:5173**.

To try an account, use the seed test user:

| Email | Password |
|---|---|
| `test@campuscustoms.yale.edu` | `password` |

You can also create a new account.

## 5. Things to try

| Where | What to do |
|---|---|
| Products page | Use the category buttons, the "In stock in" size filter, and sort by price. |
| Chat (the red **Ask** seal, bottom right) | "What hoodies do you have?" Cards appear on a "Staff picks" shelf at the top of the page; click one to open its product page. |
| Any product page, e.g. Boola Boola T Shirt | Ask "Do you have this in large?" (it's sold out in L), then "What else could I get?" to see in-stock alternatives in L. |
| Replies with prices or stock | Look for the green **✓ Checked against inventory** stamp. |
| Chat history | Log in, chat, log out, and log back in: your history reloads. Guest chats are never saved. |

## Notes

- **Safety:** agent tools are read-only. There are per-message limits (8 model requests, 8 tool calls, 60k tokens), and `output/audit_trail.json` records tool activity without any names, emails, or message text. See `output/harness.md` for details.
- **Kept out of git** by `.gitignore`: `.env`, `data/` (the database, product images, and backup), `.venv/`, and `node_modules/`.
