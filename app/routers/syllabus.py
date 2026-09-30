"""Syllabus ingestion API endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Objective, SubTopic, Syllabus, Topic
from app.schemas import SyllabusInput, SyllabusResponse
from app.services.syllabus_pdf_parser import normalise_form, parse_syllabus_pdf

router = APIRouter(prefix="/api/syllabus", tags=["syllabus"])


@router.post("/", response_model=SyllabusResponse, status_code=status.HTTP_201_CREATED)
def create_syllabus(payload: SyllabusInput, db: Session = Depends(get_db)):
    """Create a syllabus with all nested topics, sub-topics, and objectives."""
    return save_syllabus(payload, db)


def _parse_upload(file: UploadFile):
    data = file.file.read()
    if not data[:5].startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="Uploaded file is not a PDF")
    try:
        parsed = parse_syllabus_pdf(data)
    except Exception as exc:  # pdfplumber raises many different errors
        raise HTTPException(status_code=422, detail=f"Could not read syllabus PDF: {exc}")
    if not parsed.forms:
        raise HTTPException(
            status_code=422,
            detail="No competence matrix found. Is this a TIE 2023 O-Level syllabus?",
        )
    return parsed


@router.post("/parse-pdf")
def parse_pdf(file: UploadFile = File(...), subject: Optional[str] = Form(None)):
    """Parse a TIE syllabus PDF and return the structured syllabus for every Form (not saved)."""
    parsed = _parse_upload(file)
    return {
        "subject": subject or parsed.subject,
        "periods_per_week": parsed.periods_per_week,
        "forms": {f: parsed.to_syllabus_input(f, subject) for f in parsed.form_names()},
    }


@router.post("/from-pdf", response_model=SyllabusResponse, status_code=status.HTTP_201_CREATED)
def create_syllabus_from_pdf(
    file: UploadFile = File(...),
    form: str = Form("Form I"),
    subject: Optional[str] = Form(None),
    periods_per_week: Optional[int] = Form(None),
    db: Session = Depends(get_db),
):
    """Upload any TIE O-Level syllabus PDF and store the chosen Form as a syllabus."""
    parsed = _parse_upload(file)
    try:
        payload = parsed.to_syllabus_input(normalise_form(form), subject)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc).strip("'\""))
    if periods_per_week:
        payload["periods_per_week"] = periods_per_week
    return save_syllabus(SyllabusInput.model_validate(payload), db)


def save_syllabus(payload: SyllabusInput, db: Session) -> Syllabus:
    """Persist a syllabus with all nested topics, sub-topics and objectives."""
    syllabus = Syllabus(
        subject=payload.subject,
        form=payload.form,
        source_note=payload.source_note,
        periods_per_week=payload.periods_per_week,
    )
    db.add(syllabus)
    db.flush()

    for topic_input in payload.topics:
        topic = Topic(
            syllabus_id=syllabus.id,
            order=topic_input.order,
            topic_id_code=topic_input.topic_id_code,
            title=topic_input.title,
        )
        db.add(topic)
        db.flush()

        for sub_topic_input in topic_input.sub_topics:
            sub_topic = SubTopic(
                topic_id=topic.id,
                order=sub_topic_input.order,
                sub_topic_id_code=sub_topic_input.sub_topic_id_code,
                title=sub_topic_input.title,
                planned_periods=sub_topic_input.planned_periods,
                competences=sub_topic_input.competences,
            )
            db.add(sub_topic)
            db.flush()

            for obj_input in sub_topic_input.objectives:
                objective = Objective(
                    sub_topic_id=sub_topic.id,
                    order=obj_input.order,
                    text=obj_input.text,
                    periods=obj_input.periods,
                    teaching_methods=obj_input.teaching_methods,
                    resources=obj_input.resources,
                    assessment_criteria=obj_input.assessment_criteria,
                )
                db.add(objective)

    db.commit()
    db.refresh(syllabus)
    return syllabus


@router.get("/", response_model=list[SyllabusResponse])
def list_syllabuses(db: Session = Depends(get_db)):
    """List all syllabuses (with nested data)."""
    syllabuses = db.query(Syllabus).all()
    return syllabuses


@router.get("/{syllabus_id}", response_model=SyllabusResponse)
def get_syllabus(syllabus_id: int, db: Session = Depends(get_db)):
    """Get a single syllabus with all nested topics, sub-topics, and objectives."""
    syllabus = db.query(Syllabus).filter(Syllabus.id == syllabus_id).first()
    if not syllabus:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Syllabus with id {syllabus_id} not found",
        )
    return syllabus
