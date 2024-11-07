from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List
from .models import Poll, Option, Vote, OTP, SessionLocal
from .utils import generate_otp

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


class Usernames(BaseModel):
    # usernames: str
    usernames: List[str]


## CRUD Endpoints
# Create Poll Endpoint
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


# Get Polls Endpoint
@app.get("/polls/{poll_id}", response_model=PollResponse)
def get_poll(poll_id: int, db: Session = Depends(get_db)):
    poll = db.query(Poll).filter(Poll.id == poll_id).first()
    if poll is None:
        raise HTTPException(status_code=404, detail="Poll not found")
    return poll


# Voting Endpoint
@app.post("/polls/{poll_id}/vote", response_model=dict)
def vote_on_poll(
    poll_id: int,
    vote: VoteCreate,
    username: str,
    otp: str,
    db: Session = Depends(get_db),
):
    # Validate OTP
    otp_record = db.query(OTP).filter(OTP.username == username, OTP.otp == otp).first()
    if otp_record is None:
        raise HTTPException(status_code=401, detail="Invalid OTP")

    # Validate option
    option = (
        db.query(Option)
        .filter(Option.id == vote.option_id, Option.poll_id == poll_id)
        .first()
    )
    if option is None:
        raise HTTPException(status_code=404, detail="Option not found for this poll")

    # Cast vote
    db_vote = Vote(option_id=option.id)
    db.add(db_vote)
    db.commit()

    # Delete OTP after use
    # db.delete(otp_record)
    # db.commit()

    return {"message": "Vote cast successfully"}


@app.delete("/polls/{poll_id}", response_model=dict)
def delete_poll(poll_id: int, db: Session = Depends(get_db)):
    poll = db.query(Poll).filter(Poll.id == poll_id).first()
    if poll is None:
        raise HTTPException(status_code=404, detail="Poll not found")
    db.delete(poll)
    db.commit()
    return {"message": "Poll deleted successfully"}


# OTP Generation Endpoint
@app.post("/generate_otps")
def generate_otps(usernames: Usernames, db: Session = Depends(get_db)):
    # username_list = usernames.usernames.splitlines()

    for username in usernames.usernames:
        otp = generate_otp()
        db_otp = OTP(username=username, otp=otp)
        db.add(db_otp)
    db.commit()
    return {"message": "OTPs generated successfully"}
