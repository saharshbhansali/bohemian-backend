from sqlalchemy.orm import Session
from .models import Candidate, Vote


def calculate_traditional_votes(election_id: int, db: Session):
    candidate_votes = {
        candidate.id: 0
        for candidate in db.query(Candidate)
        .filter(Candidate.election_id == election_id)
        .all()
    }
    votes = (
        db.query(Vote)
        .join(Candidate)
        .filter(Candidate.election_id == election_id)
        .all()
    )
    for vote in votes:
        candidate_votes[vote.candidate_id] += 1
    # print(votes)
    # print(candidate_votes)
    return candidate_votes


def calculate_ranked_choice_votes(election_id: int, db: Session):
    # Implement ranked choice voting logic
    pass


def calculate_score_votes(election_id: int, db: Session):
    # Implement score voting logic
    pass


def calculate_quadratic_votes(election_id: int, db: Session):
    # Implement quadratic voting logic
    pass
