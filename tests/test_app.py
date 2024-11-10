from fastapi.testclient import TestClient
from fastapi import Response
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

SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)

election_ids = {}


@pytest.fixture(scope="function")
def db():
    Base.metadata.create_all(bind=engine)
    yield TestingSessionLocal()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
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
        otp = generate_otp()
        with open("identities.csv", mode="a") as file:
            writer = csv.DictWriter(file, fieldnames=["email", "otp"])
            writer.writerow({"email": email, "otp": otp})
    hashed_otp = hash_email_otp(email, otp)
    print(f"Hashed OTP for {email}: {hashed_otp}")  # Debug statement

    hashed_otp = hash_email_otp(email, otp)

    # Cast vote
    response = client.post(
        f"/elections/{election_id}/vote",
        headers={"Authorization": f"Bearer {hashed_otp}"},
        json=vote_data,
    )

    assert response.status_code == 200
    assert response.json() == {"message": "Vote cast successfully"}


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
@pytest.mark.parametrize(
    "email, vote_index, election_type",
    [
        ("user1@example.com", 0, "traditional"),
        ("user2@example.com", 1, "traditional"),
        ("user3@example.com", 0, "traditional"),
    ],
)
def test_vote_in_election(client, election_data, email, vote_index, election_type):
    election_ids, election_responses = election_data
    election_id = election_ids[election_type]
    candidates = election_responses[election_type]["candidates"]

    vote_data = {"vote": candidates[vote_index]["id"]}
    cast_vote(client, email, vote_data, election_id)


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
    # if data.get("winner"):
    if "winner" in data:
        assert data["winner"]["name"] == "Candidate 1"
    else:
        assert data["winner"] is None
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


@pytest.mark.parametrize(
    "election_data",
    [
        {
            "election_type": "ranked_choice",
            "title": "Ranked Choice Election",
            "candidates": ["Candidate 1", "Candidate 2", "Candidate 3"],
            "voter_emails": [
                "user1@example.com",
                "user2@example.com",
                "user3@example.com",
                "user4@example.com",
                "user5@example.com",
                "user6@example.com",
            ],
        },
    ],
    indirect=True,
)
@pytest.mark.parametrize(
    "email, vote_indices, election_type",
    [
        ("user1@example.com", [0, 1, 2], "ranked_choice"),
        ("user2@example.com", [1, 2, 0], "ranked_choice"),
        ("user3@example.com", [2, 0, 1], "ranked_choice"),
        ("user4@example.com", [0, 1, 2], "ranked_choice"),
        ("user5@example.com", [1, 2, 0], "ranked_choice"),
        ("user6@example.com", [2, 0, 1], "ranked_choice"),
    ],
)
def test_vote_in_ranked_choice_election(
    client, election_data, email, vote_indices, election_type
):
    election_ids, election_responses = election_data
    election_id = election_ids[election_type]
    candidates = election_responses[election_type]["candidates"]

    vote_data = {
        str(candidates[i]["id"]): rank + 1
        for rank, i in enumerate(vote_indices)
        if i < len(candidates)
    }
    cast_vote(client, email, {"vote": json.dumps(vote_data)}, election_id)


@pytest.mark.parametrize(
    "election_data",
    [
        {
            "election_type": "score_voting",
            "title": "Score Election",
            "candidates": ["Candidate 1", "Candidate 2", "Candidate 3"],
            "voter_emails": [
                "user1@example.com",
                "user2@example.com",
                "user3@example.com",
                "user4@example.com",
                "user5@example.com",
                "user6@example.com",
            ],
        },
    ],
    indirect=True,
)
@pytest.mark.parametrize(
    "email, vote_indices, election_type",
    [
        ("user1@example.com", [0, 1, 2], "score_voting"),
        ("user2@example.com", [1, 1, 1], "score_voting"),
        ("user3@example.com", [3, 0, 0], "score_voting"),
        ("user4@example.com", [1, 3, 2], "score_voting"),
        ("user5@example.com", [1, 1, 1], "score_voting"),
        ("user6@example.com", [2, 0, 1], "score_voting"),
    ],
)
def test_vote_in_score_voting_election(
    client, election_data, email, vote_indices, election_type
):
    election_ids, election_responses = election_data
    election_id = election_ids[election_type]
    candidates = election_responses[election_type]["candidates"]

    vote_data = {
        str(candidates[i]["id"]): score + 1
        for score, i in enumerate(vote_indices)
        if i < len(candidates)
    }
    cast_vote(client, email, {"vote": json.dumps(vote_data)}, election_id)


@pytest.mark.parametrize(
    "election_data",
    [
        {
            "election_type": "quadratic_voting",
            "title": "Quadratic Election",
            "candidates": ["Candidate 1", "Candidate 2", "Candidate 3"],
            "voter_emails": [
                "user1@example.com",
                "user2@example.com",
                "user3@example.com",
                "user4@example.com",
                "user5@example.com",
                "user6@example.com",
            ],
        },
    ],
    indirect=True,
)
@pytest.mark.parametrize(
    "email, vote_indices, election_type",
    [
        ("user1@example.com", [20, 30, 50], "quadratic_voting"),
        ("user2@example.com", [34, 33, 33], "quadratic_voting"),
        ("user3@example.com", [60, 20, 20], "quadratic_voting"),
        ("user4@example.com", [10, 00, 90], "quadratic_voting"),
        ("user5@example.com", [40, 35, 25], "quadratic_voting"),
        ("user6@example.com", [100, 0, 00], "quadratic_voting"),
    ],
)
def test_vote_in_quadratic_voting_election(
    client, election_data, email, vote_indices, election_type
):
    election_ids, election_responses = election_data
    election_id = election_ids[election_type]
    candidates = election_responses[election_type]["candidates"]

    vote_data = {
        str(candidates[i]["id"]): vote
        for i, vote in enumerate(vote_indices)
        if i < len(candidates)
    }
    cast_vote(client, email, {"vote": json.dumps(vote_data)}, election_id)
