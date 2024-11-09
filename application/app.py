import logging
import json
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, HTTPException, Depends, Request, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Dict
from .models import (
    Election,
    Candidate,
    Vote,
    AlternativeVote,
    OTP,
    ElectionWinner,
    SessionLocal,
)
from .utils import (
    generate_otp,
    hash_email_otp,
    send_email,
    handle_otp_storage_and_notification,
)
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from datetime import datetime, UTC as datetime_UTC
from .vote_calculation import (
    calculate_traditional_votes,
    calculate_ranked_choice_votes,
    calculate_score_votes,
    calculate_quadratic_votes,
)

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
    vote: int


class AlternativeVoteCreate(BaseModel):
    vote: str


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
    end_time: datetime
    voting_system: str


class ElectionResponse(BaseModel):
    id: int
    title: str
    candidates: List[CandidateResponse]


class ElectionWinnerResponse(BaseModel):
    id: int
    name: str
    votes: int


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

    handle_otp_storage_and_notification(
        usernames.usernames, otps, send_emails=SEND_EMAILS, write_to_csv=WRITE_TO_CSV
    )

    return {"message": "OTPs generated and stored successfully"}


## CRUD Endpoints


# Create election
@app.post("/elections/", response_model=ElectionResponse)
def create_election(election: ElectionCreate, db: Session = Depends(get_db)):
    db_election = Election(
        title=election.title,
        end_time=election.end_time,
        voting_system=election.voting_system,
    )
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
    vote: VoteCreate | AlternativeVoteCreate,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
):
    validation_token = credentials.credentials
    # Validate OTP
    otp_record = db.query(OTP).filter(OTP.otp == validation_token).first()
    if otp_record is None:
        raise HTTPException(status_code=401, detail="Invalid OTP")

    election = db.query(Election).filter(Election.id == election_id).first()

    if election.voting_system == "traditional" and type(vote.vote) == type(0):
        # Traditional voting logic
        candidate = (
            db.query(Candidate)
            .filter(Candidate.id == vote.vote, Candidate.election_id == election_id)
            .first()
        )
        if candidate is None:
            raise HTTPException(
                status_code=404, detail="Candidate not found for this election"
            )
        db_vote = Vote(
            validation_token=validation_token,
            election_id=election.id,
            candidate_id=candidate.id,
        )
        db.add(db_vote)
    elif election.voting_system in (
        "ranked_choice",
        "score_voting",
        "quadratic_voting",
    ) and type(vote.vote) == type(""):
        # Parse the JSON data
        # sample: '{"id1":1, "id2":2, "id3":3, "id4":4}'
        vote_data = json.loads(vote.vote)
        for candidate_id in vote_data:
            if (
                not db.query(Candidate)
                .filter(
                    Candidate.id == candidate_id, Candidate.election_id == election_id
                )
                .first()
            ):
                raise HTTPException(
                    status_code=404,
                    detail=f"Candidate with ID {candidate_id} not found for this election",
                )

        db_vote = AlternativeVote(
            validation_token=validation_token,
            election_id=election.id,
            # vote=str.encode(vote.vote),
            vote=vote.vote,
        )
        db.add(db_vote)
    else:
        raise HTTPException(
            status_code=400,
            detail="Invalid voting system and/or vote type for this election",
        )

    db.commit()
    db.delete(otp_record)
    db.commit()
    return {"message": "Vote cast successfully"}


class ElectionResultsResponse(BaseModel):
    results: List[CandidateResponse]
    winner: CandidateResponse = None
    is_draw: bool = False


# Get election results
@app.get("/elections/{election_id}/results", response_model=ElectionResultsResponse)
def get_election_results(election_id: int, db: Session = Depends(get_db)):
    election = db.query(Election).filter(Election.id == election_id).first()
    if not election:
        raise HTTPException(status_code=404, detail="Election not found")

    candidates = db.query(Candidate).filter(Candidate.election_id == election_id).all()
    if not candidates:
        raise HTTPException(
            status_code=404, detail="No candidates found for this election"
        )

    # Calculate votes for each candidate
    if election.voting_system == "traditional":
        candidate_votes = calculate_traditional_votes(election_id, db)
    elif election.voting_system == "ranked_choice":
        candidate_votes = calculate_ranked_choice_votes(election_id, db)
    elif election.voting_system == "score_voting":
        candidate_votes = calculate_score_votes(election_id, db)
    elif election.voting_system == "quadratic_voting":
        candidate_votes = calculate_quadratic_votes(election_id, db)
    else:
        raise HTTPException(status_code=400, detail="Invalid voting system")

    # Create response with vote counts
    results = [
        CandidateResponse(
            id=candidate.id, name=candidate.name, votes=candidate_votes[candidate.id]
        )
        for candidate in candidates
    ]

    # Sort candidates by votes in descending order
    results.sort(key=lambda candidate: candidate.votes, reverse=True)

    # Check if the election has expired
    if election.end_time and datetime.now(datetime_UTC) > election.end_time.replace(
        tzinfo=datetime_UTC
    ):
        # Check for draw
        max_votes = results[0].votes
        top_candidates = [
            candidate for candidate in results if candidate.votes == max_votes
        ]
        if len(top_candidates) > 1:
            return ElectionResultsResponse(results=results, is_draw=True)

        winner = results[0]
        # Store the winner in the ElectionWinner table
        db_winner = ElectionWinner(election_id=election.id, winner_id=winner.id)
        db.add(db_winner)
        db.commit()
        return ElectionResultsResponse(results=results, winner=winner)

    return ElectionResultsResponse(results=results)
