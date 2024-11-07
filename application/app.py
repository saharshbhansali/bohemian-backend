from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List
from .models import Poll, Option, Vote, SessionLocal

app = FastAPI()


# Dependency to get the DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Pydantic Models
class OptionCreate(BaseModel):
    text: str


class OptionResponse(BaseModel):
    id: int
    text: str


class PollCreate(BaseModel):
    question: str
    options: List[OptionCreate]


class PollResponse(BaseModel):
    id: int
    question: str
    options: List[OptionResponse]


class VoteCreate(BaseModel):
    option_id: int


# CRUD Endpoints
@app.post("/polls/", response_model=PollResponse)
def create_poll(poll: PollCreate, db: Session = Depends(get_db)):
    db_poll = Poll(question=poll.question)
    db.add(db_poll)
    db.commit()
    db.refresh(db_poll)

    options = []
    for option in poll.options:
        db_option = Option(text=option.text, poll_id=db_poll.id)
        db.add(db_option)
        db.commit()
        db.refresh(db_option)
        options.append(db_option)

    db_poll.options = options
    return db_poll


@app.get("/polls/{poll_id}", response_model=PollResponse)
def get_poll(poll_id: int, db: Session = Depends(get_db)):
    poll = db.query(Poll).filter(Poll.id == poll_id).first()
    if poll is None:
        raise HTTPException(status_code=404, detail="Poll not found")
    return poll


@app.post("/polls/{poll_id}/vote", response_model=dict)
def vote_on_poll(poll_id: int, vote: VoteCreate, db: Session = Depends(get_db)):
    option = (
        db.query(Option)
        .filter(Option.id == vote.option_id, Option.poll_id == poll_id)
        .first()
    )
    if option is None:
        raise HTTPException(status_code=404, detail="Option not found for this poll")
    db_vote = Vote(option_id=option.id)
    db.add(db_vote)
    db.commit()
    return {"message": "Vote cast successfully"}


@app.delete("/polls/{poll_id}", response_model=dict)
def delete_poll(poll_id: int, db: Session = Depends(get_db)):
    poll = db.query(Poll).filter(Poll.id == poll_id).first()
    if poll is None:
        raise HTTPException(status_code=404, detail="Poll not found")
    db.delete(poll)
    db.commit()
    return {"message": "Poll deleted successfully"}
