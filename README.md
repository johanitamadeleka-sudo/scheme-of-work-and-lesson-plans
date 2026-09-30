# Scheme of Work & Lesson Plan Generator

A FastAPI application that automatically generates **Schemes of Work** and **Lesson Plans** as `.docx` documents from structured syllabus and academic calendar data.

Built for the Tanzania O-Level secondary education system. It works for **any subject**: give it an official TIE 2023 syllabus PDF and it reads the competence matrix, fits the periods to the academic calendar and writes the scheme of work and lesson plans.

Bundled syllabi (from the [TIE lower-secondary syllabus page](https://www.tie.go.tz/publications/syllabus-for-lower-secondary-academics)): Mathematics, Physics, Chemistry, Biology, Geography, History, Computer Science and English Language.

## Features

- **Any-subject PDF import** - Parse any TIE 2023 O-Level syllabus PDF (main competence -> specific competence -> learning activities with their methods, resources, assessment criteria and periods), for all four Forms, including the subject's periods per week
- **Syllabus Management** - Store and retrieve structured syllabus data (topics, sub-topics, competences, objectives)
- **Academic Calendar** - Define terms, teaching weeks, holidays, and examination periods with period budgets
- **Textbook References** - Link textbook entries to sub-topics for automatic citation in outputs
- **Allocation Engine** - Distribute competences across teaching weeks using the subject's periods per week (e.g. Physics 3, Mathematics 5), with an optional *fit* mode that scales syllabus periods so the scheme fills the calendar exactly
- **Activity-aware output** - Each scheme row lists only the learning activities taught that week, with the syllabus' own methods, resources and assessment criteria; each lesson plan targets the activity for its period
- **Scheme of Work Generation** - Produce a complete scheme of work table with all 12 columns (week, dates, topic, sub-topic, periods, objectives, teaching/learning strategies, resources, assessment, references, remarks, teacher's self-evaluation)
- **Lesson Plan Generation** - Generate per-period lesson plans with stages (Introduction, Development, Consolidation, Conclusion), timing, teacher/student activities, and assessment
- **DOCX Export** - Download publication-ready `.docx` files for both scheme of work and lesson plans

## Prerequisites

- Python 3.11 or higher (3.12 recommended)
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

## Installation & Setup

```bash
# Clone the repository
git clone https://github.com/kiyaboapp/scheme-of-work-and-lesson-plans.git
cd scheme-of-work-and-lesson-plans

# Create virtual environment and install dependencies (using uv)
uv venv venv
uv pip install -e '.[dev]'

# Or using pip
python -m venv venv
source venv/bin/activate
pip install -e '.[dev]'
```

## Quick Start

### Scheme of work for any subject (recommended)

```bash
# Physics Form I: scheme + lesson plans into examples/
venv/bin/python seed/generate_scheme.py \
    --syllabus "assets/syllabus/PHYSICS SYLLABUS - O Level 2023.pdf" --form "Form I"

# All four Forms of Geography, schemes only
venv/bin/python seed/generate_scheme.py \
    --syllabus "assets/syllabus/GEOGRAPHY SYLLABUS - O Level 2023.pdf" --form all --no-lesson-plans

# A new subject: download its PDF from TIE and point at it
venv/bin/python seed/generate_scheme.py --syllabus path/to/SUBJECT.pdf --form F2 \
    --textbook "TIE (2023), Subject for Secondary Schools Book 2"
```

Options: `--periods-per-week N` (override the syllabus), `--fit scale|shrink|none`
(default `scale` fills the calendar exactly; `shrink` only scales down on overflow;
`none` keeps syllabus periods), `--calendar path.json` (default
`data/calendars/tanzania_secondary_2026.json`), `--export-json DIR` (write the
parsed syllabus as editable JSON instead of generating documents). Parsed JSON for
every bundled subject/Form is already in `data/syllabi/` - edit one and pass it as
`--syllabus data/syllabi/physics_form_i.json`.

The script uses an in-memory database, so it never touches `sow_generator.db`.

### 1. Seed the Database

Populate the database with Form I Mathematics syllabus, 2026 academic calendar, textbook references, and run the allocation engine:

```bash
venv/bin/python seed/seed_form1_math.py
```

This creates `sow_generator.db` (SQLite) with:
- 3 topics, 5 sub-topics totaling 175 periods
- 2 terms with 35 teaching weeks (5 periods/week)
- 5 textbook entries
- 36 allocation assignments covering all 175 periods

### 2. Generate Example DOCX Files

Run the full pipeline (fresh database, seed, then generate documents):

```bash
venv/bin/python seed/generate_examples.py
```

This produces two files in the `examples/` directory:
- `Scheme_of_Work_Form1_Mathematics_2026.docx` - Complete scheme of work table
- `Lesson_Plans_Form1_Mathematics_2026.docx` - All lesson plans for the year

### 3. Start the API Server

```bash
venv/bin/python -m uvicorn app.main:app --reload
```

The server runs at `http://localhost:8000`. Interactive API docs are available at `http://localhost:8000/docs`.

## API Endpoints

### Syllabus

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/syllabus/` | Create a new syllabus with topics and sub-topics |
| POST | `/api/syllabus/from-pdf` | Upload a TIE syllabus PDF (multipart: `file`, `form`, optional `subject`, `periods_per_week`) and store that Form |
| POST | `/api/syllabus/parse-pdf` | Upload a TIE syllabus PDF and preview the parsed syllabus for every Form (not saved) |
| GET | `/api/syllabus/` | List all syllabuses |
| GET | `/api/syllabus/{id}` | Get a syllabus by ID with full nested structure |

### Calendar

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/calendar/` | Create an academic calendar with terms and weeks |
| GET | `/api/calendar/` | List all calendars |
| GET | `/api/calendar/{id}` | Get a calendar by ID with terms and weeks |

### Textbook

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/textbook/` | Create textbook reference entries (bulk) |
| GET | `/api/textbook/` | List all textbook entries |

### Allocation

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/allocate` | Run the allocation engine. Body: `syllabus_id`, `calendar_id`, optional `periods_per_week`, `fit` (`none` default, `shrink`, `scale`) |
| GET | `/api/allocate/{syllabus_id}/{calendar_id}` | Retrieve existing allocation results |

### Scheme of Work

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/scheme/{syllabus_id}/{calendar_id}` | Generate scheme of work (JSON) |
| GET | `/api/scheme/{syllabus_id}/{calendar_id}/docx` | Download scheme of work as .docx |

### Lesson Plans

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/lesson-plan/{syllabus_id}/{calendar_id}/week/{week_number}` | Get lesson plans for a week (JSON) |
| GET | `/api/lesson-plan/{syllabus_id}/{calendar_id}/week/{week_number}/period/{period_number}` | Get a single lesson plan (JSON) |
| GET | `/api/lesson-plan/{syllabus_id}/{calendar_id}/docx` | Download all lesson plans as .docx |

## Examples Directory

The `examples/` directory contains pre-generated `.docx` files that demonstrate what the system produces:

- **Scheme_of_Work_{Physics,Chemistry,Biology,Geography,History,English_Language,Computer_Science}_Form_I_2026.docx** (+ Computer Science Form II) - generated straight from the TIE PDFs with `seed/generate_scheme.py`
- **Lesson_Plans_Physics_Form_I_2026.docx** - 105 Physics lesson plans (3 periods/week)

- **Scheme_of_Work_Form1_Mathematics_2026.docx** - A complete scheme of work for Form I Basic Mathematics covering the 2026 academic year. Contains a 12-column table with topics allocated across 35 teaching weeks.
- **Lesson_Plans_Form1_Mathematics_2026.docx** - Individual lesson plans for every teaching period (175 total). Each plan includes learning objectives, teaching stages with timing, teacher and student activities, and assessment criteria.

These files are generated from the Form I Mathematics seed data and serve as reference examples of the output format.

## How the any-subject pipeline works

1. **Parse** (`app/services/syllabus_pdf_parser.py`) - every TIE 2023 O-Level syllabus uses the same 7-column matrix. Rows are read with pdfplumber; continuation rows across pages are merged, the Form is tracked from the "Form I / Form One" headings, and section 10.0 gives periods per week. Periods printed once per specific competence (Physics) or once per activity (Geography) are both supported.
2. **Allocate** (`app/services/allocation.py`) - weekly budget = subject periods per week (short weeks scaled). With `fit=scale` the competence periods are scaled with the largest-remainder method (min 1 each) to exactly fill the calendar, then packed week by week in syllabus order.
3. **Map activities** (`app/services/activity_mapping.py`) - each week's share of a competence is mapped back to its learning activities, so scheme rows and lesson plans show the right activity, methods, resources and assessment criteria.

## Running Tests

```bash
# Run all tests with verbose output
venv/bin/python -m pytest tests/ -v

# Run a specific test file
venv/bin/python -m pytest tests/test_docx_generation.py -v
```

## Project Structure

```
app/
  main.py              - FastAPI application entry point
  database.py          - SQLAlchemy engine and session setup
  models.py            - ORM models (Syllabus, Topic, SubTopic, Calendar, Term, Week, etc.)
  schemas.py           - Pydantic request/response schemas
  routers/             - API route handlers
  services/            - Business logic (PDF parser, allocation, activity mapping, scheme generation, docx writers)
seed/
  seed_form1_math.py   - Seed script with Form I Mathematics data
  generate_examples.py - Runner that seeds + generates the Mathematics example .docx files
  generate_scheme.py   - Any-subject generator: TIE syllabus PDF/JSON -> scheme + lesson plans
data/
  calendars/           - Reusable academic calendars (2026)
  syllabi/             - Parsed syllabus JSON for every bundled subject and Form
examples/              - Pre-generated .docx output files
tests/                 - pytest test suite
assets/                - Source PDFs and sample documents
tools/                 - Text extractions from source documents
```

## Technology Stack

- **FastAPI** - Web framework
- **SQLAlchemy** - ORM and database management
- **Pydantic** - Data validation and serialization
- **python-docx** - DOCX file generation
- **pdfplumber** - Syllabus PDF table extraction
- **SQLite** - Database (file-based, no server required)
- **pytest + httpx** - Testing
