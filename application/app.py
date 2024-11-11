import logging
import json
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, HTTPException, Depends, Request, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, constr
from typing import List, Dict
from .models import (
    Election,
    Candidate,
    Vote,
    AlternativeVote,
    AuthorizationToken,
    ElectionWinner,
    SessionLocal,
)
from .utils import (
    generate_otp,
    create_auth_token,
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


class emails(BaseModel):
    # emails: str
    emails: List[str]


class CandidateCreate(BaseModel):
    name: str


class CandidateResponse(BaseModel):
    id: int
    name: str
    votes: float


class ElectionCreate(BaseModel):
    title: str
    voting_system: str = Field(
        ..., pattern="^(traditional|ranked_choice|score_voting|quadratic_voting)$"
    )
    end_time: datetime
    candidates: List[CandidateCreate]
    voter_emails: List[str]


class ElectionResponse(BaseModel):
    id: int
    title: str
    candidates: List[CandidateResponse]


class ElectionResultsResponse(BaseModel):
    election_title: str
    voting_system: str = Field(
        ..., pattern="^(traditional|ranked_choice|score_voting|quadratic_voting)$"
    )
    results: List[CandidateResponse]
    winner: CandidateResponse = None
    is_draw: bool = False


security = HTTPBearer()

SEND_EMAILS = False  # Set to True to enable email sending
WRITE_TO_CSV = True  # Set to True to enable writing to CSV


## CRUD Endpoints


# Create an election, and geenrate and send OTPs
@app.post("/elections/", response_model=ElectionResponse)
def create_election(election: ElectionCreate, db: Session = Depends(get_db)):

    # Create election
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

    # To clear out the OTP table: db.query(OTP).delete(synchronize_session=False)
    # Generate OTPs
    email_otp_mapping = {}
    for email in election.voter_emails:
        otp = generate_otp()
        auth_token = create_auth_token(email, otp)
        db_auth = AuthorizationToken(auth_token=auth_token, election_id=db_election.id)
        db.add(db_auth)
        email_otp_mapping[email] = otp
    db.commit()
    handle_otp_storage_and_notification(
        db_election.id,
        db_election.title,
        email_otp_mapping,
        send_emails=SEND_EMAILS,
        write_to_csv=WRITE_TO_CSV,
    )

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
    # Validate auth_token
    auth_token_record = (
        db.query(AuthorizationToken)
        .filter(
            (AuthorizationToken.auth_token == validation_token)
            & (AuthorizationToken.election_id == election_id)
        )
        .first()
    )
    if auth_token_record is None:
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
            vote_string=vote.vote,
            vote=str.encode(vote.vote),
        )
        db.add(db_vote)
    else:
        raise HTTPException(
            status_code=400,
            detail="Invalid voting system and/or vote type for this election",
        )

    db.commit()
    db.delete(auth_token_record)
    db.commit()
    return {"message": "Vote cast successfully"}


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

    # Check if the election has expired
    if election.end_time and datetime.now(datetime_UTC) > election.end_time.replace(
        tzinfo=datetime_UTC
    ):
        # Check if the winner has already been decided and stored
        stored_winner = (
            db.query(ElectionWinner)
            .filter(ElectionWinner.election_id == election_id)
            .first()
        )
        if stored_winner and stored_winner.winner_id:
            winner_candidate = (
                db.query(Candidate)
                .filter(Candidate.id == stored_winner.winner_id)
                .first()
            )
            results = [
                CandidateResponse(
                    id=candidate.id,
                    name=candidate.name,
                    votes=candidate.votes,
                )
                for candidate in candidates
            ]
            results.sort(key=lambda candidate: candidate.votes, reverse=True)
            return ElectionResultsResponse(
                election_title=election.title,
                voting_system=election.voting_system,
                results=results,
                winner=CandidateResponse(
                    id=winner_candidate.id,
                    name=winner_candidate.name,
                    votes=stored_winner.votes,
                ),
            )
        elif stored_winner and stored_winner.winner_id is None:
            results = [
                CandidateResponse(
                    id=candidate.id,
                    name=candidate.name,
                    votes=candidate.votes,
                )
                for candidate in candidates
            ]
            results.sort(key=lambda candidate: candidate.votes, reverse=True)
            return ElectionResultsResponse(
                election_title=election.title,
                voting_system=election.voting_system,
                results=results,
                winner=None,
                is_draw=True,
            )
        else:
            pass

    # Calculate votes for each candidate
    if election.voting_system == "traditional":
        candidate_votes = calculate_traditional_votes(election_id, db)

        for candidate in candidates:
            candidate.votes = candidate_votes[candidate.id]
        db.commit()

        # Create response with vote counts
        results = [
            CandidateResponse(
                id=candidate.id,
                name=candidate.name,
                votes=candidate_votes[candidate.id],
            )
            for candidate in candidates
        ]

        # Sort candidates by votes in descending order
        results.sort(key=lambda candidate: candidate.votes, reverse=True)

    elif election.voting_system == "ranked_choice":
        candidate_votes = calculate_ranked_choice_votes(election_id, db)
        # print(candidate_votes)

        for candidate in candidates:
            candidate.votes = candidate_votes[candidate.id]
        db.commit()

        results = [
            CandidateResponse(
                id=candidate.id,
                name=candidate.name,
                votes=candidate_votes[candidate.id],
            )
            for candidate in candidates
            if candidate.id in candidate_votes.keys()
        ]
    elif election.voting_system == "score_voting":
        candidate_votes = calculate_score_votes(election_id, db)
    elif election.voting_system == "quadratic_voting":
        candidate_votes = calculate_quadratic_votes(election_id, db)
    else:
        raise HTTPException(status_code=400, detail="Invalid voting system")

    # Check if the election has expired
    if election.end_time and datetime.now(datetime_UTC) > election.end_time.replace(
        tzinfo=datetime_UTC
    ):
        # print(results)
        # Check for draw
        max_votes = results[0].votes
        top_candidates = [
            candidate for candidate in results if candidate.votes == max_votes
        ]
        if len(top_candidates) > 1:
            db_draw = ElectionWinner(
                election_id=election.id, winner_id=None, votes=max_votes
            )
            db.add(db_draw)
            db.commit()

            return ElectionResultsResponse(
                election_title=election.title,
                voting_system=election.voting_system,
                results=results,
                is_draw=True,
            )

        winner = results[0]
        # Store the winner in the ElectionWinner table
        db_winner = ElectionWinner(
            election_id=election.id, winner_id=winner.id, votes=winner.votes
        )
        db.add(db_winner)
        db.commit()
        return ElectionResultsResponse(
            election_title=election.title,
            voting_system=election.voting_system,
            results=results,
            winner=winner,
        )

    return ElectionResultsResponse(
        election_title=election.title,
        voting_system=election.voting_system,
        results=results,
    )
