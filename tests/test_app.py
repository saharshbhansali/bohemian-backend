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
import logging

SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)


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
def election_data(client):
    # Create elections once per module
    election_ids = {}
    election_responses = {}

    # Traditional Election
    response = client.post(
        "/elections/",
        json={
            "title": "Traditional Election",
            "voting_system": "traditional",
            "end_time": (datetime.now(datetime_UTC) + timedelta(days=1)).isoformat(),
            "candidates": [{"name": name} for name in ["Candidate 1", "Candidate 2"]],
            "voter_emails": [
                "trad_user1@example.com",
                "trad_user2@example.com",
                "trad_user3@example.com",
            ],
        },
    )
    assert response.status_code == 200
    data = response.json()
    election_ids["traditional"] = data["id"]
    election_responses["traditional"] = data

    # Traditional Election (Draw)
    response = client.post(
        "/elections/",
        json={
            "title": "Traditional Election (Draw)",
            "voting_system": "traditional",
            "end_time": (datetime.now(datetime_UTC) + timedelta(days=1)).isoformat(),
            "candidates": [{"name": name} for name in ["Candidate 1", "Candidate 2"]],
            "voter_emails": [
                "draw_user1@example.com",
                "draw_user2@example.com",
            ],
        },
    )
    assert response.status_code == 200
    data = response.json()
    election_ids["traditional_draw"] = data["id"]
    election_responses["traditional_draw"] = data

    # Ranked Choice Election
    response = client.post(
        "/elections/",
        json={
            "title": "Ranked Choice Election",
            "voting_system": "ranked_choice",
            "end_time": (datetime.now(datetime_UTC) + timedelta(days=1)).isoformat(),
            "candidates": [
                {"name": name} for name in ["Candidate 1", "Candidate 2", "Candidate 3"]
            ],
            "voter_emails": [
                "rank_user1@example.com",
                "rank_user2@example.com",
                "rank_user3@example.com",
                "rank_user4@example.com",
                "rank_user5@example.com",
                "rank_user6@example.com",
            ],
        },
    )
    assert response.status_code == 200
    data = response.json()
    election_ids["ranked_choice"] = data["id"]
    election_responses["ranked_choice"] = data

    # Score Voting Election
    response = client.post(
        "/elections/",
        json={
            "title": "Score Election",
            "voting_system": "score_voting",
            "end_time": (datetime.now(datetime_UTC) + timedelta(days=1)).isoformat(),
            "candidates": [
                {"name": name} for name in ["Candidate 1", "Candidate 2", "Candidate 3"]
            ],
            "voter_emails": [
                "score_user1@example.com",
                "score_user2@example.com",
                "score_user3@example.com",
                "score_user4@example.com",
                "score_user5@example.com",
                "score_user6@example.com",
            ],
        },
    )
    assert response.status_code == 200
    data = response.json()
    election_ids["score_voting"] = data["id"]
    election_responses["score_voting"] = data

    # Quadratic Voting Election
    response = client.post(
        "/elections/",
        json={
            "title": "Quadratic Election",
            "voting_system": "quadratic_voting",
            "end_time": (datetime.now(datetime_UTC) + timedelta(days=1)).isoformat(),
            "candidates": [
                {"name": name} for name in ["Candidate 1", "Candidate 2", "Candidate 3"]
            ],
            "voter_emails": [
                "quad_user1@example.com",
                "quad_user2@example.com",
                "quad_user3@example.com",
                "quad_user4@example.com",
                "quad_user5@example.com",
                "quad_user6@example.com",
            ],
        },
    )
    assert response.status_code == 200
    data = response.json()
    election_ids["quadratic_voting"] = data["id"]
    election_responses["quadratic_voting"] = data

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
        # Generate a new OTP and save it to identities.csv
        logging.error("OTP not found for %s", email)
        assert False
    hashed_otp = hash_email_otp(email, otp)
    print(f"Hashed OTP for {email}: {hashed_otp}")  # Debug statement

    # Cast vote
    response = client.post(
        f"/elections/{election_id}/vote",
        headers={"Authorization": f"Bearer {hashed_otp}"},
        json=vote_data,
    )

    assert response.status_code == 200
    assert response.json() == {"message": "Vote cast successfully"}


@pytest.mark.parametrize(
    "email, vote_index, election_type",
    [
        ("trad_user1@example.com", 0, "traditional"),
        ("trad_user2@example.com", 1, "traditional"),
        ("trad_user3@example.com", 0, "traditional"),
    ],
)
def test_vote_in_election(client, election_data, email, vote_index, election_type):
    election_ids, election_responses = election_data
    election_id = election_ids[election_type]
    candidates = election_responses[election_type]["candidates"]
    logging.error("Election variables:\n%s\n%s", election_ids, election_responses)

    vote_data = {"vote": candidates[vote_index]["id"]}
    cast_vote(client, email, vote_data, election_id)


@patch("application.app.datetime")
def test_get_election_results(mock_datetime, client, election_data):
    election_ids, election_responses = election_data
    election_id = election_ids["traditional"]
    candidates = election_responses["traditional"]["candidates"]
    logging.error("Election variables:\n%s\n%s", election_ids, election_responses)

    cast_vote(
        client, "trad_user1@example.com", {"vote": candidates[0]["id"]}, election_id
    )
    cast_vote(
        client, "trad_user2@example.com", {"vote": candidates[1]["id"]}, election_id
    )
    cast_vote(
        client, "trad_user3@example.com", {"vote": candidates[0]["id"]}, election_id
    )

    # Mock current time to simulate election expiry
    mock_datetime.now.return_value = datetime.now(datetime_UTC) + timedelta(days=2)

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
    assert data["winner"]["name"] == "Candidate 1"


@patch("application.app.datetime")
def test_get_election_results_draw(mock_datetime, client, election_data):
    election_ids, election_responses = election_data
    logging.error("Election variables:\n%s\n%s", election_ids, election_responses)
    election_id = election_ids["traditional_draw"]
    candidates = election_responses["traditional_draw"]["candidates"]

    cast_vote(
        client, "draw_user1@example.com", {"vote": candidates[0]["id"]}, election_id
    )
    cast_vote(
        client, "draw_user2@example.com", {"vote": candidates[1]["id"]}, election_id
    )

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
    "email, vote_indices, election_type",
    [
        ("rank_user1@example.com", [0, 1, 2], "ranked_choice"),
        ("rank_user2@example.com", [1, 2, 0], "ranked_choice"),
        ("rank_user3@example.com", [2, 0, 1], "ranked_choice"),
        ("rank_user4@example.com", [0, 1, 2], "ranked_choice"),
        ("rank_user5@example.com", [1, 2, 0], "ranked_choice"),
        ("rank_user6@example.com", [2, 0, 1], "ranked_choice"),
    ],
)
def test_vote_in_ranked_choice_election(
    client, election_data, email, vote_indices, election_type
):
    election_ids, election_responses = election_data
    election_id = election_ids[election_type]
    candidates = election_responses[election_type]["candidates"]
    logging.error("Election variables:\n%s\n%s", election_ids, election_responses)

    vote_data = {
        str(candidates[i]["id"]): rank + 1
        for rank, i in enumerate(vote_indices)
        if i < len(candidates)
    }
    cast_vote(client, email, {"vote": json.dumps(vote_data)}, election_id)


@pytest.mark.skip(reason="Score voting not implemented")
@patch("application.app.datetime")
def test_get_ranked_choice_election_results(mock_datetime, client, election_data):
    election_ids, election_responses = election_data
    election_id = election_ids["ranked_choice"]
    candidates = election_responses["ranked_choice"]["candidates"]
    logging.error("Election variables:\n%s\n%s", election_ids, election_responses)

    # Cast votes
    votes = [
        ("rank_user1@example.com", [0, 1, 2]),
        ("rank_user2@example.com", [1, 2, 0]),
        ("rank_user3@example.com", [2, 0, 1]),
        ("rank_user4@example.com", [0, 1, 2]),
        ("rank_user5@example.com", [1, 2, 0]),
        ("rank_user6@example.com", [2, 0, 1]),
    ]
    for email, vote_indices in votes:
        vote_data = {
            str(candidates[i]["id"]): rank + 1 for rank, i in enumerate(vote_indices)
        }
        cast_vote(client, email, {"vote": json.dumps(vote_data)}, election_id)

    # Mock current time to simulate election expiry
    mock_datetime.now.return_value = datetime.now(datetime_UTC) + timedelta(days=2)

    # Get election results
    response = client.get(f"/elections/{election_id}/results")
    assert response.status_code == 200
    data = response.json()

    # Verify the results
    assert "results" in data
    assert "winner" in data
    assert data["voting_system"] == "ranked_choice"
    assert data["is_draw"] is False
    expected_winner = candidates[1]  # Adjust index based on expected winner
    assert data["winner"]["name"] == expected_winner["name"]


@pytest.mark.parametrize(
    "email, vote_indices, election_type",
    [
        ("score_user1@example.com", [3, 2, 1], "score_voting"),
        ("score_user2@example.com", [1, 1, 1], "score_voting"),
        ("score_user3@example.com", [3, 0, 0], "score_voting"),
        ("score_user4@example.com", [1, 3, 2], "score_voting"),
        ("score_user5@example.com", [1, 1, 1], "score_voting"),
        ("score_user6@example.com", [2, 0, 1], "score_voting"),
    ],
)
def test_vote_in_score_voting_election(
    client, election_data, email, vote_indices, election_type
):
    election_ids, election_responses = election_data
    election_id = election_ids[election_type]
    candidates = election_responses[election_type]["candidates"]
    logging.error("Election variables:\n%s\n%s", election_ids, election_responses)

    vote_data = {
        str(candidates[i]["id"]): score + 1
        for i, score in enumerate(vote_indices)
        if i < len(candidates)
    }
    cast_vote(client, email, {"vote": json.dumps(vote_data)}, election_id)


@pytest.mark.skip(reason="Quadratic voting not implemented")
@pytest.mark.parametrize(
    "email, vote_indices, election_type",
    [
        ("quad_user1@example.com", [20, 30, 50], "quadratic_voting"),
        ("quad_user2@example.com", [34, 33, 33], "quadratic_voting"),
        ("quad_user3@example.com", [60, 20, 20], "quadratic_voting"),
        ("quad_user4@example.com", [10, 0, 90], "quadratic_voting"),
        ("quad_user5@example.com", [40, 35, 25], "quadratic_voting"),
        ("quad_user6@example.com", [100, 0, 0], "quadratic_voting"),
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
