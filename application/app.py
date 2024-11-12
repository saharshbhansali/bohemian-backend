import logging
import json
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, HTTPException, Depends, Request, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, constr
from typing import List, Dict, Optional
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
    id: int | None = None
    name: str | None = None
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
    results: List[CandidateResponse] | None = None
    winner: List[CandidateResponse] | None = None
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

    def candidate_votes_winner_calculate(
        election_id: int, db: Session
    ) -> List[Optional[List[CandidateResponse]]]:

        # election = db.query(Election).filter(Election.id == election_id).first()
        # if not election:
        #     raise HTTPException(status_code=404, detail="Election not found")

        # candidates = (
        #     db.query(Candidate).filter(Candidate.election_id == election_id).all()
        # )
        # if not candidates:
        #     raise HTTPException(
        #         status_code=404, detail="No candidates found for this election"
        #     )

        stored_winner = (
            db.query(ElectionWinner)
            .filter(ElectionWinner.election_id == election_id)
            .first()
        )

        # Check if the election has a stored winner
        if stored_winner:
            candidate_votes = [
                CandidateResponse(
                    id=candidate.id, name=candidate.name, votes=candidate.votes
                )
                for candidate in candidates
            ]

            if stored_winner.winner_id:
                winner = [
                    CandidateResponse(
                        id=stored_winner.winner_id,
                        name=stored_winner.winner.name,
                        votes=stored_winner.votes,
                    )
                ]

            else:
                winner = [
                    CandidateResponse(id=None, name=None, votes=stored_winner.votes)
                ]

            return [candidate_votes, winner]

        else:
            candidate_votes = {}
            if election.voting_system == "traditional":
                candidate_votes = calculate_traditional_votes(election_id, db)
            elif election.voting_system == "ranked_choice":
                candidate_votes = calculate_ranked_choice_votes(election_id, db)
            elif election.voting_system == "score_voting":
                candidate_votes = calculate_score_votes(election_id, db)
            elif election.voting_system == "quadratic_voting":
                candidate_votes = calculate_quadratic_votes(election_id, db)
            # else:
            #     return [None, None]

            print(
                f"Candidate Votes returned from calculate_system_votes: {candidate_votes}"
            )

            for candidate in candidates:
                if candidate.id not in candidate_votes:
                    candidate_votes[candidate.id] = 0.0
                else:
                    candidate.votes = candidate_votes[candidate.id]

            winner = max(candidates, key=lambda x: x.votes)
            winner_ids = {
                candidate.id: [candidate.name, candidate.votes]
                for candidate in candidates
                if candidate.votes == winner.votes
            }
            if len(winner_ids) > 1:
                db_winner = ElectionWinner(
                    election_id=election_id,
                    winner_id=None,
                    votes=winner.votes,
                )

            elif len(winner_ids) == 1:
                db_winner = ElectionWinner(
                    election_id=election_id,
                    winner_id=winner.id,
                    votes=winner.votes,
                )
            else:
                db_winner = None

            if db_winner:
                db.add(db_winner)
                db.commit()

        return [
            [
                CandidateResponse(
                    id=candidate.id, name=candidate.name, votes=candidate.votes
                )
                for candidate in candidates
            ],
            [
                CandidateResponse(
                    id=winner_id,
                    name=winner_ids[winner_id][0],
                    votes=winner_ids[winner_id][1],
                )
                for winner_id in winner_ids
            ],
        ]

    election = db.query(Election).filter(Election.id == election_id).first()
    if not election:
        raise HTTPException(status_code=404, detail="Election not found")

    candidates = db.query(Candidate).filter(Candidate.election_id == election_id).all()
    if not candidates:
        raise HTTPException(
            status_code=404, detail="No candidates found for this election"
        )

    # Check if the election has expired and calculate the winner
    candidate_responses, winners = None, None
    if election.end_time and datetime.now(datetime_UTC) > election.end_time.replace(
        tzinfo=datetime_UTC
    ):
        candidate_responses, winners = candidate_votes_winner_calculate(election_id, db)
    else:
        candidate_votes = calculate_ranked_choice_votes(
            election_id, db, traditional=True
        )
        print(
            f"Traditional Votes for alt systems while the election is going on: {candidate_votes}"
        )
        for candidate in candidates:
            if candidate.id not in candidate_votes:
                candidate_votes[candidate.id] = 0.0
            else:
                candidate.votes = candidate_votes[candidate.id]
        candidate_responses = [
            CandidateResponse(
                id=candidate.id,
                name=candidate.name,
                votes=candidate.votes,
            )
            for candidate in candidates
        ]

    if not candidate_responses:
        raise HTTPException(
            status_code=404, detail="No results found for this election"
        )

    if winners and winners[0].id is None and winners[0].name == "Draw":
        return ElectionResultsResponse(
            election_title=election.title,
            voting_system=election.voting_system,
            results=candidate_responses,
            winner=winners[0],
            is_draw=True,
        )
    else:
        return ElectionResultsResponse(
            election_title=election.title,
            voting_system=election.voting_system,
            results=candidate_responses,
            winner=winners,
        )
