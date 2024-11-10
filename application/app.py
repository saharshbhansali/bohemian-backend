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
    logger.info("Creating election with title: %s", election.title)
    # Generate OTPs
    db.query(AuthorizationToken).delete(synchronize_session=False)
    email_otp_mapping = {}
    for email in election.voter_emails:
        otp = generate_otp()
        hashed_token = create_auth_token(email, otp)
        db_auth_token = AuthorizationToken(token=hashed_token)
        db.add(db_auth_token)
        email_otp_mapping[email] = otp
        logger.debug("Generated OTP for %s: %s", email, otp)
        logger.debug("Created hashed token for %s: %s", email, hashed_token)
    db.commit()
    logger.info("Authorization tokens committed to the database")
    handle_otp_storage_and_notification(
        email_otp_mapping, send_emails=SEND_EMAILS, write_to_csv=WRITE_TO_CSV
    )
    logger.info("Handled OTP storage and notification")

    # Create election
    db_election = Election(
        title=election.title,
        end_time=election.end_time,
        voting_system=election.voting_system,
    )
    db.add(db_election)
    db.commit()
    db.refresh(db_election)
    logger.info("Election created with ID: %d", db_election.id)
    candidates = []
    for candidate in election.candidates:
        db_candidate = Candidate(name=candidate.name, election_id=db_election.id)
        db.add(db_candidate)
        db.commit()
        db.refresh(db_candidate)
        candidates.append(db_candidate)
        logger.debug("Candidate added: %s", candidate.name)
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
    logger.info("Received vote for election ID: %d", election_id)
    logger.debug("Validation token: %s", validation_token)
    # Validate OTP
    token_record = (
        db.query(AuthorizationToken)
        .filter(AuthorizationToken.token == validation_token)
        .first()
    )
    if token_record is None:
        logger.warning("Invalid OTP for token: %s", validation_token)
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
            logger.error("Candidate not found for election ID: %d", election_id)
            raise HTTPException(
                status_code=404, detail="Candidate not found for this election"
            )
        db_vote = Vote(
            validation_token=validation_token,
            election_id=election.id,
            candidate_id=candidate.id,
        )
        db.add(db_vote)
        logger.info("Vote added for candidate ID: %d", candidate.id)
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
                logger.error(
                    "Candidate with ID %s not found for election ID: %d",
                    candidate_id,
                    election_id,
                )
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
        logger.info("Alternative vote added for election ID: %d", election_id)
    else:
        logger.error(
            "Invalid voting system and/or vote type for election ID: %d", election_id
        )
        raise HTTPException(
            status_code=400,
            detail="Invalid voting system and/or vote type for this election",
        )

    db.commit()
    db.delete(validation_token)
    db.commit()
    logger.info("Vote cast successfully for election ID: %d", election_id)
    return {"message": "Vote cast successfully"}


# Get election results
@app.get("/elections/{election_id}/results", response_model=ElectionResultsResponse)
def get_election_results(election_id: int, db: Session = Depends(get_db)):
    logger.info("Fetching results for election ID: %d", election_id)
    election = db.query(Election).filter(Election.id == election_id).first()
    if not election:
        logger.error("Election not found with ID: %d", election_id)
        raise HTTPException(status_code=404, detail="Election not found")

    candidates = db.query(Candidate).filter(Candidate.election_id == election_id).all()
    if not candidates:
        logger.error("No candidates found for election ID: %d", election_id)
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
        if stored_winner:
            winner_candidate = (
                db.query(Candidate)
                .filter(Candidate.id == stored_winner.winner_id)
                .first()
            )
            results = [
                CandidateResponse(
                    id=candidate.id,
                    name=candidate.name,
                    votes=winner_candidate.votes,
                )
                for candidate in candidates
            ]
            results.sort(key=lambda candidate: candidate.votes, reverse=True)
            logger.info(
                "Returning stored election results for election ID: %d", election_id
            )
            return ElectionResultsResponse(
                voting_system=election.voting_system,
                results=results,
                winner=CandidateResponse(
                    id=winner_candidate.id,
                    name=winner_candidate.name,
                    votes=winner_candidate.votes,
                ),
            )
        else:
            pass

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
        logger.error("Invalid voting system for election ID: %d", election_id)
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
            logger.info("Election ID: %d resulted in a draw", election_id)
            return ElectionResultsResponse(
                voting_system=election.voting_system, results=results, is_draw=True
            )

        winner = results[0]
        # Store the winner in the ElectionWinner table
        db_winner = ElectionWinner(
            election_id=election.id, winner_id=winner.id, votes=winner.votes
        )
        db.add(db_winner)
        db.commit()
        logger.info("Winner stored for election ID: %d", election_id)
        return ElectionResultsResponse(
            voting_system=election.voting_system,
            results=results,
            winner=winner,
        )

    logger.info("Returning election results for election ID: %d", election_id)
    return ElectionResultsResponse(
        voting_system=election.voting_system, results=results
    )


# @app.get("/verify_token/{token}", response_model=dict)
# def verify_token(token: str, db: Session = Depends(get_db)):
#     logger.info("Verifying token: %s", token)
#     token_record = (
#         db.query(AuthorizationToken).filter(AuthorizationToken.token == token).first()
#     )
#     if token_record:
#         logger.info("Token exists: %s", token)
#         return {"status": "Token exists"}
#     else:
#         logger.warning("Token does not exist: %s", token)
#         return {"status": "Token does not exist"}
