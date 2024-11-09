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

SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)


def get_otp_from_csv(email):
    with open("identities.csv", mode="r") as file:
        reader = csv.DictReader(file)
        for row in reader:
            if row["email"] == email:
                return row["otp"]
    return None


def cast_vote(email, vote_data, election_id):
    otp = get_otp_from_csv(email)
    if otp is None:
        raise ValueError(f"OTP for {email} not found in identities.csv")

    hashed_otp = hash_email_otp(email, otp)

    # Cast vote
    response = client.post(
        f"/elections/{election_id}/vote",
        headers={"Authorization": f"Bearer {hashed_otp}"},
        json=vote_data,
    )

    assert response.status_code == 200
    assert response.json() == {"message": "Vote cast successfully"}


@pytest.mark.skip(reason="This endpoint and test has been deprecated.")
def test_generate_otps():
    response = client.post(
        "/generate_otps",
        json={
            "usernames": ["user1@example.com", "user2@example.com", "user3@example.com"]
        },
    )
    assert response.status_code == 200
    assert response.json() == {"message": "OTPs generated and stored successfully"}


def test_create_election() -> Response:
    response = client.post(
        "/elections/",
        json={
            "title": "Test Election",
            "voting_system": "traditional",
            "end_time": (datetime.now(datetime_UTC) + timedelta(days=1)).isoformat(),
            "candidates": [{"name": "Candidate 1"}, {"name": "Candidate 2"}],
            "voter_emails": [
                "user1@example.com",
                "user2@example.com",
                "user3@example.com",
            ],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Test Election"
    assert len(data["candidates"]) == 2
    assert data["candidates"][0]["name"] == "Candidate 1"
    assert data["candidates"][1]["name"] == "Candidate 2"

    return response


def test_vote_in_election() -> int:
    response = test_create_election()
    election_id = response.json()["id"]
    candidates = response.json()["candidates"]

    cast_vote("user1@example.com", {"vote": candidates[0]["id"]}, election_id)
    cast_vote("user2@example.com", {"vote": candidates[1]["id"]}, election_id)
    cast_vote("user3@example.com", {"vote": candidates[0]["id"]}, election_id)
    # cast_vote("user3@example.com", {"vote": "{'c1':1, 'c2':2, 'c3':3, 'c4':4}"}, election_id)

    return election_id


@patch("application.app.datetime")
def test_get_election_results(mock_datetime):
    election_id = test_vote_in_election()

    # Mock current time to simulate election expiry
    mock_datetime.now.return_value = datetime.now(datetime_UTC) + timedelta(days=2)

    response = client.get(f"/elections/{election_id}/results")
    assert response.status_code == 200
    data = response.json()
    assert "results" in data
    assert "winner" in data
    assert len(data["results"]) == 2
    assert data["results"][0]["name"] == "Candidate 1"
    assert data["results"][1]["name"] == "Candidate 2"
    assert data["winner"]["name"] == "Candidate 1"


@patch("application.app.datetime")
def test_get_election_results_draw(mock_datetime):
    response = test_create_election()
    election_id = response.json()["id"]
    candidates = response.json()["candidates"]

    cast_vote("user1@example.com", {"vote": candidates[0]["id"]}, election_id)
    cast_vote("user2@example.com", {"vote": candidates[1]["id"]}, election_id)

    # Mock current time to simulate election expiry
    mock_datetime.now.return_value = datetime.now(datetime_UTC) + timedelta(days=2)

    response = client.get(f"/elections/{election_id}/results")
    assert response.status_code == 200
    data = response.json()
    assert "results" in data
    assert "is_draw" in data
    assert data["is_draw"] is True
    assert len(data["results"]) == 2
    assert data["results"][0]["name"] == "Candidate 1"
    assert data["results"][1]["name"] == "Candidate 2"


def test_create_ranked_choice_election() -> Response:
    response = client.post(
        "/elections/",
        json={
            "title": "Ranked Choice Election",
            "voting_system": "ranked_choice",
            "end_time": (datetime.now(datetime_UTC) + timedelta(days=1)).isoformat(),
            "candidates": [
                {"name": "Candidate 1"},
                {"name": "Candidate 2"},
                {"name": "Candidate 3"},
            ],
            "voter_emails": [
                "user1@example.com",
                "user2@example.com",
                "user3@example.com",
            ],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Ranked Choice Election"
    assert len(data["candidates"]) == 3
    assert data["candidates"][0]["name"] == "Candidate 1"
    assert data["candidates"][1]["name"] == "Candidate 2"
    assert data["candidates"][2]["name"] == "Candidate 3"

    return response


def test_create_score_voting_election() -> Response:
    response = client.post(
        "/elections/",
        json={
            "title": "Score Voting Election",
            "voting_system": "score_voting",
            "end_time": (datetime.now(datetime_UTC) + timedelta(days=1)).isoformat(),
            "candidates": [
                {"name": "Candidate 1"},
                {"name": "Candidate 2"},
                {"name": "Candidate 3"},
            ],
            "voter_emails": [
                "user1@example.com",
                "user2@example.com",
                "user3@example.com",
            ],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Score Voting Election"
    assert len(data["candidates"]) == 3
    assert data["candidates"][0]["name"] == "Candidate 1"
    assert data["candidates"][1]["name"] == "Candidate 2"
    assert data["candidates"][2]["name"] == "Candidate 3"

    return response


def test_create_quadratic_voting_election() -> Response:
    response = client.post(
        "/elections/",
        json={
            "title": "Quadratic Voting Election",
            "voting_system": "quadratic_voting",
            "end_time": (datetime.now(datetime_UTC) + timedelta(days=1)).isoformat(),
            "candidates": [
                {"name": "Candidate 1"},
                {"name": "Candidate 2"},
                {"name": "Candidate 3"},
            ],
            "voter_emails": [
                "user1@example.com",
                "user2@example.com",
                "user3@example.com",
            ],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Quadratic Voting Election"
    assert len(data["candidates"]) == 3
    assert data["candidates"][0]["name"] == "Candidate 1"
    assert data["candidates"][1]["name"] == "Candidate 2"
    assert data["candidates"][2]["name"] == "Candidate 3"

    return response


def test_vote_in_ranked_choice_election() -> int:
    response = test_create_ranked_choice_election()
    election_id = response.json()["id"]
    candidates = response.json()["candidates"]

    c1 = candidates[0]["id"]
    c2 = candidates[1]["id"]
    c3 = candidates[2]["id"]

    vote1 = {str(c1): 1, str(c2): 2, str(c3): 3}
    vote2 = {str(c1): 2, str(c2): 3, str(c3): 1}
    vote3 = {str(c1): 3, str(c2): 1, str(c3): 2}

    cast_vote("user1@example.com", {"vote": str(vote1).replace("'", '"')}, election_id)
    cast_vote("user2@example.com", {"vote": str(vote2).replace("'", '"')}, election_id)
    cast_vote("user3@example.com", {"vote": str(vote3).replace("'", '"')}, election_id)

    return election_id


def test_vote_in_score_voting_election() -> int:
    response = test_create_score_voting_election()
    election_id = response.json()["id"]
    candidates = response.json()["candidates"]

    c1 = candidates[0]["id"]
    c2 = candidates[1]["id"]
    c3 = candidates[2]["id"]

    vote1 = {str(c1): 1, str(c2): 2, str(c3): 3}
    vote2 = {str(c1): 2, str(c2): 2, str(c3): 2}
    vote3 = {str(c1): 4, str(c2): 1, str(c3): 1}

    cast_vote("user1@example.com", {"vote": str(vote1).replace("'", '"')}, election_id)
    cast_vote("user2@example.com", {"vote": str(vote2).replace("'", '"')}, election_id)
    cast_vote("user3@example.com", {"vote": str(vote3).replace("'", '"')}, election_id)

    return election_id


def test_vote_in_quadratic_voting_election() -> int:
    response = test_create_quadratic_voting_election()
    election_id = response.json()["id"]
    candidates = response.json()["candidates"]

    c1 = candidates[0]["id"]
    c2 = candidates[1]["id"]
    c3 = candidates[2]["id"]

    vote1 = {str(c1): 20, str(c2): 30, str(c3): 50}
    vote2 = {str(c1): 34, str(c2): 33, str(c3): 33}
    vote3 = {str(c1): 60, str(c2): 20, str(c3): 20}

    cast_vote("user1@example.com", {"vote": str(vote1).replace("'", '"')}, election_id)
    cast_vote("user2@example.com", {"vote": str(vote2).replace("'", '"')}, election_id)
    cast_vote("user3@example.com", {"vote": str(vote3).replace("'", '"')}, election_id)

    return election_id


@pytest.mark.skip(reason="This test is not implemented yet.")
@patch("application.app.datetime")
def test_get_ranked_choice_election_results(mock_datetime):
    election_id = test_vote_in_ranked_choice_election()

    # Mock current time to simulate election expiry
    mock_datetime.now.return_value = datetime.now(datetime_UTC) + timedelta(days=2)

    response = client.get(f"/elections/{election_id}/results")
    assert response.status_code == 200
    data = response.json()
    assert "results" in data
    assert "winner" in data
    assert len(data["results"]) == 3


@pytest.mark.skip(reason="This test is not implemented yet.")
@patch("application.app.datetime")
def test_get_score_voting_election_results(mock_datetime):
    election_id = test_vote_in_score_voting_election()

    # Mock current time to simulate election expiry
    mock_datetime.now.return_value = datetime.now(datetime_UTC) + timedelta(days=2)

    response = client.get(f"/elections/{election_id}/results")
    assert response.status_code == 200
    data = response.json()
    assert "results" in data
    assert "winner" in data
    assert len(data["results"]) == 3


@pytest.mark.skip(reason="This test is not implemented yet.")
@patch("application.app.datetime")
def test_get_quadratic_voting_election_results(mock_datetime):
    election_id = test_vote_in_quadratic_voting_election()

    # Mock current time to simulate election expiry
    mock_datetime.now.return_value = datetime.now(datetime_UTC) + timedelta(days=2)

    response = client.get(f"/elections/{election_id}/results")
    assert response.status_code == 200
    data = response.json()
    assert "results" in data
    assert "winner" in data
    assert len(data["results"]) == 3
