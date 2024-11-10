from fastapi.testclient import TestClient
from fastapi import Response, HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from application.app import app, get_db
from application.models import Base, Election, Candidate, OTP
from application.utils import generate_otp, hash_email_otp
from datetime import datetime, timedelta, UTC as datetime_UTC
from unittest.mock import patch
import csv
import pytest
import json
import logging

SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)

election_ids = {}


@pytest.fixture(scope="module")
def db():
    Base.metadata.create_all(bind=engine)
    yield TestingSessionLocal()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="module")
def client():
    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


@pytest.fixture(scope="module")
def setup_elections(client):
    election_data = {
        "traditional": {
            "election_type": "traditional",
            "title": "Traditional Election",
            "candidates": ["Candidate 1", "Candidate 2"],
            "voter_emails": [
                "user11@example.com",
                "user21@example.com",
                "user31@example.com",
            ],
        },
        "ranked_choice": {
            "election_type": "ranked_choice",
            "title": "Ranked Choice Election",
            "candidates": ["Candidate 1", "Candidate 2", "Candidate 3"],
            "voter_emails": [
                "user12@example.com",
                "user22@example.com",
                "user32@example.com",
                "user42@example.com",
                "user52@example.com",
                "user62@example.com",
            ],
        },
        "score_voting": {
            "election_type": "score_voting",
            "title": "Score Election",
            "candidates": ["Candidate 1", "Candidate 2", "Candidate 3"],
            "voter_emails": [
                "user13@example.com",
                "user23@example.com",
                "user33@example.com",
                "user43@example.com",
                "user53@example.com",
                "user63@example.com",
            ],
        },
        "quadratic_voting": {
            "election_type": "quadratic_voting",
            "title": "Quadratic Election",
            "candidates": ["Candidate 1", "Candidate 2", "Candidate 3"],
            "voter_emails": [
                "user14@example.com",
                "user24@example.com",
                "user34@example.com",
                "user44@example.com",
                "user54@example.com",
                "user64@example.com",
            ],
        },
    }

    elections = {}
    for key, data in election_data.items():
        response = client.post(
            "/elections/",
            json={
                "title": data["title"],
                "voting_system": data["election_type"],
                "end_time": (
                    datetime.now(datetime_UTC) + timedelta(days=1)
                ).isoformat(),
                "candidates": [{"name": candidate} for candidate in data["candidates"]],
                "voter_emails": data["voter_emails"],
            },
        )
        assert response.status_code == 200
        elections[key] = response.json()

    return elections


@pytest.fixture(scope="function")
def election_data(request, client):
    election_ids = {}
    election_responses = {}

    def create_election(election_type, title, candidates, voter_emails, draw=False):
        response = client.post(
            "/elections/",
            json={
                "title": title,
                "voting_system": election_type,
                "end_time": (
                    datetime.now(datetime_UTC) + timedelta(days=1)
                ).isoformat(),
                "candidates": [{"name": candidate} for candidate in candidates],
                "voter_emails": voter_emails,
            },
        )
        assert response.status_code == 200
        data = response.json()
        if draw:
            election_type += "_draw"
        election_ids[election_type] = data["id"]
        election_responses[election_type] = data

    create_election(**request.param)

    return election_ids, election_responses


def get_otp_from_csv(email):
    with open("identities.csv", mode="r") as file:
        reader = csv.DictReader(file)
        for row in reader:
            if row["email"] == email:
                print(f"Found OTP for {email}: {row['otp']}")  # Debug statement
                return row["otp"]
    print(f"OTP for {email} not found in identities.csv")  # Debug statement
    return None


def cast_vote(client, email, vote_data, election_id):
    otp = get_otp_from_csv(email)
    if otp is None:
        logging.error(f"OTP for {email} not found in identities.csv")
        return HTTPException(
            status_code=404, detail=f"OTP for {email} not found in identities.csv"
        )
    hashed_otp = hash_email_otp(email, otp)
    print(f"Hashed OTP for {email}: {hashed_otp}")  # Debug statement
    response = client.post(
        f"/elections/{election_id}/vote",
        headers={"Authorization": f"Bearer {hashed_otp}"},
        json=vote_data,
    )

    assert response.status_code == 200
    assert response.json() == {"message": "Vote cast successfully"}


@pytest.fixture
def vote_in_traditional_election(client, setup_elections):
    election_data = setup_elections["traditional"]
    election_id = election_data["id"]
    candidates = election_data["candidates"]

    def _vote(email, vote_index):
        vote_data = {"vote": candidates[vote_index]["id"]}
        cast_vote(client, email, vote_data, election_id)

    return _vote


@pytest.fixture
def vote_in_ranked_choice_election(client, setup_elections):
    election_data = setup_elections["ranked_choice"]
    election_id = election_data["id"]
    candidates = election_data["candidates"]

    def _vote(email, vote_indices):
        vote_data = {
            str(candidates[i]["id"]): rank + 1
            for rank, i in enumerate(vote_indices)
            if i < len(candidates)
        }
        cast_vote(client, email, {"vote": json.dumps(vote_data)}, election_id)

    return _vote


@pytest.fixture
def vote_in_score_voting_election(client, setup_elections):
    election_data = setup_elections["score_voting"]
    election_id = election_data["id"]
    candidates = election_data["candidates"]

    def _vote(email, vote_indices):
        vote_data = {
            str(candidates[i]["id"]): score + 1
            for score, i in enumerate(vote_indices)
            if i < len(candidates)
        }
        cast_vote(client, email, {"vote": json.dumps(vote_data)}, election_id)

    return _vote


@pytest.fixture
def vote_in_quadratic_voting_election(client, setup_elections):
    election_data = setup_elections["quadratic_voting"]
    election_id = election_data["id"]
    candidates = election_data["candidates"]

    def _vote(email, vote_indices):
        vote_data = {
            str(candidates[i]["id"]): vote
            for i, vote in enumerate(vote_indices)
            if i < len(candidates)
        }
        cast_vote(client, email, {"vote": json.dumps(vote_data)}, election_id)

    return _vote


@pytest.mark.parametrize(
    "email, vote_index",
    [
        ("user11@example.com", 0),
        ("user21@example.com", 1),
        ("user31@example.com", 0),
    ],
)
def test_vote_in_traditional_election(vote_in_traditional_election, email, vote_index):
    vote_in_traditional_election(email, vote_index)


@pytest.mark.parametrize(
    "email, vote_indices",
    [
        ("user12@example.com", [0, 1, 2]),
        ("user22@example.com", [1, 2, 0]),
        ("user32@example.com", [2, 0, 1]),
        ("user42@example.com", [0, 1, 2]),
        ("user52@example.com", [1, 2, 0]),
        ("user62@example.com", [2, 0, 1]),
    ],
)
def test_vote_in_ranked_choice_election(
    vote_in_ranked_choice_election, email, vote_indices
):
    vote_in_ranked_choice_election(email, vote_indices)


@pytest.mark.parametrize(
    "email, vote_indices",
    [
        ("user13@example.com", [0, 1, 2]),
        ("user23@example.com", [1, 1, 1]),
        ("user33@example.com", [3, 0, 0]),
        ("user43@example.com", [1, 3, 2]),
        ("user53@example.com", [1, 1, 1]),
        ("user63@example.com", [2, 0, 1]),
    ],
)
def test_vote_in_score_voting_election(
    vote_in_score_voting_election, email, vote_indices
):
    vote_in_score_voting_election(email, vote_indices)


@pytest.mark.parametrize(
    "email, vote_indices",
    [
        ("user14@example.com", [20, 30, 50]),
        ("user24@example.com", [34, 33, 33]),
        ("user34@example.com", [60, 20, 20]),
        ("user44@example.com", [10, 00, 90]),
        ("user54@example.com", [40, 35, 25]),
        ("user64@example.com", [100, 0, 00]),
    ],
)
def test_vote_in_quadratic_voting_election(
    vote_in_quadratic_voting_election, email, vote_indices
):
    vote_in_quadratic_voting_election(email, vote_indices)


@pytest.mark.parametrize(
    "election_data",
    [
        {
            "election_type": "traditional",
            "title": "Traditional Election",
            "candidates": ["Candidate 1", "Candidate 2"],
            "voter_emails": [
                "user1@example.com",
                "user2@example.com",
                "user3@example.com",
            ],
        },
    ],
    indirect=True,
)
@patch("application.app.datetime")
def test_get_election_results(mock_datetime, client, election_data):
    election_ids, election_responses = election_data
    election_id = election_ids["traditional"]
    candidates = election_responses["traditional"]["candidates"]

    cast_vote(client, "user1@example.com", {"vote": candidates[0]["id"]}, election_id)
    cast_vote(client, "user2@example.com", {"vote": candidates[1]["id"]}, election_id)

    # Mock current time to simulate election expiry
    mock_datetime.now.return_value = datetime.now(datetime_UTC) + timedelta(days=0.5)

    response = client.get(f"/elections/{election_id}/results")
    assert response.status_code == 200
    data = response.json()
    print(data)
    print(data["results"])
    print(data["winner"])

    assert "results" in data
    assert "is_draw" in data
    assert "voting_system" in data
    assert data["voting_system"] == "traditional"
    assert data["is_draw"] is False
    assert len(data["results"]) == 2
    assert data["results"][0]["name"] == "Candidate 1"
    assert data["results"][1]["name"] == "Candidate 2"

    cast_vote(client, "user3@example.com", {"vote": candidates[0]["id"]}, election_id)

    # Mock current time to simulate election expiry
    mock_datetime.now.return_value = datetime.now(datetime_UTC) + timedelta(days=2)

    response = client.get(f"/elections/{election_id}/results")
    assert response.status_code == 200
    data = response.json()

    assert "results" in data
    assert "voting_system" in data
    assert data["voting_system"] == "traditional"
    assert len(data["results"]) == 2
    assert data["results"][0]["name"] == "Candidate 1"
    assert data["results"][1]["name"] == "Candidate 2"

    print(data)
    print(data["results"])
    print(data["winner"])
    assert data["winner"]["name"] == "Candidate 1"


@pytest.mark.parametrize(
    "election_data",
    [
        {
            "election_type": "traditional",
            "title": "Traditional Election",
            "candidates": ["Candidate 1", "Candidate 2"],
            "voter_emails": [
                "user1@example.com",
                "user2@example.com",
            ],
            "draw": True,
        },
    ],
    indirect=True,
)
@patch("application.app.datetime")
def test_get_election_results_draw(mock_datetime, client, election_data):
    election_ids, election_responses = election_data
    election_id = election_ids["traditional_draw"]
    candidates = election_responses["traditional_draw"]["candidates"]

    cast_vote(client, "user1@example.com", {"vote": candidates[0]["id"]}, election_id)
    cast_vote(client, "user2@example.com", {"vote": candidates[1]["id"]}, election_id)

    # Mock current time to simulate election expiry
    mock_datetime.now.return_value = datetime.now(datetime_UTC) + timedelta(days=2)

    response = client.get(f"/elections/{election_id}/results")
    assert response.status_code == 200
    data = response.json()
    assert "results" in data
    assert "is_draw" in data
    assert "voting_system" in data
    assert data["voting_system"] == "traditional"
    assert data["is_draw"] is True
    assert len(data["results"]) == 2
    assert data["results"][0]["name"] == "Candidate 1"
    assert data["results"][1]["name"] == "Candidate 2"
