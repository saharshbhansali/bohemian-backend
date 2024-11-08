import logging
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, HTTPException, Depends, Request, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List
from .models import Election, Candidate, Vote, OTP, SessionLocal
from .utils import generate_otp, hash_email_otp, send_email, handle_otp_storage_and_notification
import csv
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"Request: {request.method} {request.url}")
    response = await call_next(request)
    logger.info(f"Response: {response.status_code}")
    return response


# Dependency to get the DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Pydantic Models
class VoteCreate(BaseModel):
    option_id: int


class Usernames(BaseModel):
    # usernames: str
    usernames: List[str]


class CandidateCreate(BaseModel):
    name: str


class CandidateResponse(BaseModel):
    id: int
    name: str
    votes: int


class ElectionCreate(BaseModel):
    title: str
    candidates: List[CandidateCreate]


class ElectionResponse(BaseModel):
    id: int
    title: str
    candidates: List[CandidateResponse]


security = HTTPBearer()

SEND_EMAILS = False  # Set to True to enable email sending
WRITE_TO_CSV = True  # Set to True to enable writing to CSV

# OTP Generation Endpoint
@app.post("/generate_otps")
def generate_otps(usernames: Usernames, db: Session = Depends(get_db)):
    # Delete existing OTPs
    db.query(OTP).delete(synchronize_session=False)

    otps = []
    for username in usernames.usernames:
        otp = generate_otp()
        hashed_value = hash_email_otp(username, otp)
        db_otp = OTP(otp=hashed_value)
        db.add(db_otp)
        otps.append(otp)

    db.commit()

    handle_otp_storage_and_notification(usernames.usernames, otps, send_emails=SEND_EMAILS, write_to_csv=WRITE_TO_CSV)

    return {"message": "OTPs generated and stored successfully"}


## CRUD Endpoints


# Create election
@app.post("/elections/", response_model=ElectionResponse)
def create_election(election: ElectionCreate, db: Session = Depends(get_db)):
    db_election = Election(title=election.title)
    db.add(db_election)
    db.commit()
    db.refresh(db_election)
    candidates = []
    for candidate in election.candidates:
        db_candidate = Candidate(name=candidate.name, election_id=db_election.id)
        db.add(db_candidate)
        db.commit()
        db.refresh(db_candidate)
        candidates.append(db_candidate)
    db_election.candidates = candidates
    return db_election


# Vote in an election
@app.post("/elections/{election_id}/vote", response_model=dict)
def vote_in_election(
    election_id: int,
    vote: VoteCreate,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
):
    validation_token = credentials.credentials
    # Validate OTP
    otp_record = db.query(OTP).filter(OTP.otp == validation_token).first()
    if otp_record is None:
        raise HTTPException(status_code=401, detail="Invalid OTP")
    # Validate candidate
    candidate = (
        db.query(Candidate)
        .filter(Candidate.id == vote.option_id, Candidate.election_id == election_id)
        .first()
    )
    if candidate is None:
        raise HTTPException(
            status_code=404, detail="Candidate not found for this election"
        )
    # Cast vote
    db_vote = Vote(candidate_id=candidate.id)
    db.add(db_vote)
    db.commit()
    # Delete OTP after use
    db.delete(otp_record)
    db.commit()
    return {"message": "Vote cast successfully"}


# Get election results
@app.get("/elections/{election_id}/results", response_model=List[CandidateResponse])
def get_election_results(election_id: int, db: Session = Depends(get_db)):
    candidates = db.query(Candidate).filter(Candidate.election_id == election_id).all()
    if not candidates:
        raise HTTPException(status_code=404, detail="Election not found")

    # Calculate votes for each candidate
    candidate_votes = {candidate.id: 0 for candidate in candidates}
    votes = (
        db.query(Vote)
        .join(Candidate)
        .filter(Candidate.election_id == election_id)
        .all()
    )
    for vote in votes:
        candidate_votes[vote.candidate_id] += 1

    # Create response with vote counts
    results = [
        CandidateResponse(
            id=candidate.id, name=candidate.name, votes=candidate_votes[candidate.id]
        )
        for candidate in candidates
    ]

    # Sort candidates by votes in descending order
    results.sort(key=lambda candidate: candidate.votes, reverse=True)
    return results
