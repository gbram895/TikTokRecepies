import logging
import os

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app import models
from app.auth import get_optional_user
from app.database import get_db
from app.services.recipe_extractor import extract_recipe
from app.services.tiktok_downloader import download_audio
from app.services.transcription import transcribe_audio

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger(__name__)


@router.get("/")
def index(request: Request, db: Session = Depends(get_db)):
    user = get_optional_user(request, db)
    if user:
        return RedirectResponse("/dashboard", status_code=303)
    return templates.TemplateResponse("index.html", {"request": request})


@router.get("/healthz")
def healthz():
    return {"status": "ok"}


def _user_recipes(db: Session, user: models.User):
    return (
        db.query(models.Recipe)
        .filter(models.Recipe.user_id == user.id)
        .order_by(models.Recipe.created_at.desc())
        .all()
    )


@router.get("/dashboard")
def dashboard(request: Request, db: Session = Depends(get_db)):
    user = get_optional_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "user": user, "recipes": _user_recipes(db, user), "error": None},
    )


@router.post("/transcribe")
def transcribe(request: Request, tiktok_url: str = Form(...), db: Session = Depends(get_db)):
    user = get_optional_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)

    tiktok_url = tiktok_url.strip()
    audio_path = None
    transcript = None
    try:
        video = download_audio(tiktok_url)
        audio_path = video.audio_path
        transcript = transcribe_audio(audio_path)
        data = extract_recipe(
            transcript, description=video.description, video_title=video.title
        )
        if not data["ingredients"] and not data["steps"]:
            raise ValueError(
                "Couldn't find a recipe in that video's narration or caption. "
                "Try a video with a clearer voiceover or a written ingredient list."
            )
    except Exception as exc:  # noqa: BLE001 - surfaced to the user below
        logger.exception("Failed to process TikTok URL %s", tiktok_url)
        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "user": user,
                "recipes": _user_recipes(db, user),
                "error": f"Couldn't turn that video into a recipe: {exc}",
            },
            status_code=400,
        )
    finally:
        if audio_path and os.path.exists(audio_path):
            try:
                os.remove(audio_path)
                os.rmdir(os.path.dirname(audio_path))
            except OSError:
                pass

    recipe = models.Recipe(
        user_id=user.id,
        tiktok_url=tiktok_url,
        title=data.get("title") or "Untitled recipe",
        servings=data.get("servings"),
        total_time=data.get("total_time"),
        ingredients=data.get("ingredients") or [],
        steps=data.get("steps") or [],
        transcript=transcript,
    )
    db.add(recipe)
    db.commit()
    db.refresh(recipe)
    return RedirectResponse(f"/recipe/{recipe.id}", status_code=303)


@router.get("/recipe/{recipe_id}")
def recipe_detail(recipe_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_optional_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    recipe = db.get(models.Recipe, recipe_id)
    if not recipe or recipe.user_id != user.id:
        return RedirectResponse("/dashboard", status_code=303)
    return templates.TemplateResponse(
        "recipe_detail.html", {"request": request, "user": user, "recipe": recipe}
    )


@router.post("/recipe/{recipe_id}/delete")
def recipe_delete(recipe_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_optional_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    recipe = db.get(models.Recipe, recipe_id)
    if recipe and recipe.user_id == user.id:
        db.delete(recipe)
        db.commit()
    return RedirectResponse("/dashboard", status_code=303)
