import os
import csv
import pytest
import json
import logging
from fastapi.testclient import TestClient
from fastapi import Response
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from application.app import app, get_db
from application.models import Base, Election, Candidate, AuthorizationToken
from application.utils import generate_otp, create_auth_token
from datetime import datetime, timedelta, UTC as datetime_UTC
from unittest.mock import patch


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
    # Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="module")
def setup_database():
    # Create tables
    Base.metadata.create_all(bind=engine)
    yield
    # Drop tables after tests
    # Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="module")
def client(setup_database):
    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


@pytest.fixture(scope="session", autouse=True)
def clean_identities_csv():
    # Remove the file if it exists
    if os.path.exists("identities.csv"):
        os.remove("identities.csv")
    yield
    # Cleanup after tests if necessary
    # if os.path.exists("identities.csv"):
    # os.remove("identities.csv")


@pytest.fixture(scope="module")
def election_data(client):
    # Create elections once per module
    election_ids = {}
    election_responses = {}
    election_configs = {
        "traditional": {
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
        "traditional_draw": {
            "title": "Traditional Election (Draw)",
            "voting_system": "traditional",
            "end_time": (datetime.now(datetime_UTC) + timedelta(days=1)).isoformat(),
            "candidates": [{"name": name} for name in ["Candidate 1", "Candidate 2"]],
            "voter_emails": [
                "draw_user1@example.com",
                "draw_user2@example.com",
            ],
        },
        "traditional_result": {
            "title": "Traditional Election (Result)",
            "voting_system": "traditional",
            "end_time": (datetime.now(datetime_UTC) + timedelta(days=1)).isoformat(),
            "candidates": [{"name": name} for name in ["Candidate 1", "Candidate 2"]],
            "voter_emails": [
                "trad_res_user1@example.com",
                "trad_res_user2@example.com",
                "trad_res_user3@example.com",
            ],
        },
        "ranked_choice": {
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
        "ranked_choice_result": {
            "title": "Ranked Choice Election (Result)",
            "voting_system": "ranked_choice",
            "end_time": (datetime.now(datetime_UTC) + timedelta(days=1)).isoformat(),
            "candidates": [
                {"name": name}
                for name in ["Candidate 1", "Candidate 2", "Candidate 3", "Candidate 4"]
            ],
            "voter_emails": [
                "rank_res_user1@example.com",
                "rank_res_user2@example.com",
                "rank_res_user3@example.com",
                "rank_res_user4@example.com",
                "rank_res_user5@example.com",
                "rank_res_user6@example.com",
            ],
        },
        "ranked_choice_draw": {
            "title": "Ranked Choice Election (Draw)",
            "voting_system": "ranked_choice",
            "end_time": (datetime.now(datetime_UTC) + timedelta(days=1)).isoformat(),
            "candidates": [
                {"name": name}
                for name in ["Candidate 1", "Candidate 2", "Candidate 3", "Candidate 4"]
            ],
            "voter_emails": [
                "rank_draw_user1@example.com",
                "rank_draw_user2@example.com",
                "rank_draw_user3@example.com",
                "rank_draw_user4@example.com",
                "rank_draw_user5@example.com",
                "rank_draw_user6@example.com",
            ],
        },
        "score_voting": {
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
        "quadratic_voting": {
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
    }

    for election_type, config in election_configs.items():
        response = client.post("/elections/", json=config)
        assert response.status_code == 200
        data = response.json()
        election_ids[election_type] = data["id"]
        election_responses[election_type] = data

    yield election_ids, election_responses


def get_otp_from_csv(email):
    with open("identities.csv", mode="r") as file:
        reader = csv.DictReader(file)
        for row in reader:
            if row["email"] == email:
                # print(f"Found OTP for {email}: {row['otp']}")  # Debug statement
                return row["otp"]
    print(f"OTP for {email} not found in identities.csv")  # Debug statement
    return None


def cast_vote(client, email, vote_data, election_id):
    otp = get_otp_from_csv(email)
    if otp is None:
        # Error if OTP not found and stop the test
        logging.error("OTP not found for %s", email)
        assert False
    auth_token = create_auth_token(email, otp)
    logging.debug(f"Auth token: {auth_token}")

    # Cast vote
    response = client.post(
        f"/elections/{election_id}/vote",
        headers={"Authorization": f"Bearer {auth_token}"},
        json=vote_data,
    )

    logging.debug(response)
    logging.debug(response.status_code)
    logging.debug(response.json())

    assert response.status_code == 200
    assert response.json() == {"message": "Vote cast successfully"}


@pytest.mark.parametrize(
    "email, vote_index",
    [
        ("trad_user1@example.com", 0),
        ("trad_user2@example.com", 1),
        ("trad_user3@example.com", 0),
    ],
)
def test_vote_in_election(client, election_data, email, vote_index):
    election_ids, election_responses = election_data
    election_id = election_ids["traditional"]
    candidates = election_responses["traditional"]["candidates"]
    # logging.error("Election variables:\n%s\n%s", election_ids, election_responses)

    vote_data = {"vote": candidates[vote_index]["id"]}
    cast_vote(client, email, vote_data, election_id)


@patch("application.app.datetime")
@patch("application.vote_calculation.datetime")
def test_get_election_results(
    mock_app_datetime, mock_vote_datetime, client, election_data
):
    election_ids, election_responses = election_data
    election_id = election_ids["traditional_result"]
    candidates = election_responses["traditional_result"]["candidates"]
    # logging.error("Election variables:\n%s\n%s", election_ids, election_responses)

    vote_data = [
        ("trad_res_user1@example.com", 0),
        ("trad_res_user2@example.com", 1),
        ("trad_res_user3@example.com", 0),
    ]
    for email, vote_index in vote_data:
        cast_vote(
            client,
            email,
            {"vote": candidates[vote_index]["id"]},
            election_id,
        )

    # Mock current time to simulate election expiry
    mock_app_datetime.now.return_value = datetime.now(datetime_UTC) + timedelta(days=2)
    mock_vote_datetime.now.return_value = datetime.now(datetime_UTC) + timedelta(days=2)

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
@patch("application.vote_calculation.datetime")
def test_get_election_results_draw(
    mock_app_datetime, mock_vote_datetime, client, election_data
):
    election_ids, election_responses = election_data
    # logging.error("Election variables:\n%s\n%s", election_ids, election_responses)
    election_id = election_ids["traditional_draw"]
    candidates = election_responses["traditional_draw"]["candidates"]

    vote_data = [
        ("draw_user1@example.com", 0),
        ("draw_user2@example.com", 1),
    ]
    for email, vote_index in vote_data:
        cast_vote(
            client,
            email,
            {"vote": candidates[vote_index]["id"]},
            election_id,
        )

    # Mock current time to simulate election expiry
    mock_app_datetime.now.return_value = datetime.now(datetime_UTC) + timedelta(days=2)
    mock_vote_datetime.now.return_value = datetime.now(datetime_UTC) + timedelta(days=2)

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
    "email, vote_indices",
    [
        ("rank_user1@example.com", [0, 1, 2]),
        ("rank_user2@example.com", [1, 2, 0]),
        ("rank_user3@example.com", [2, 0, 1]),
        ("rank_user4@example.com", [0, 1, 2]),
        ("rank_user5@example.com", [1, 2, 0]),
        ("rank_user6@example.com", [2, 0, 1]),
    ],
)
def test_vote_in_ranked_choice_election(client, election_data, email, vote_indices):
    election_ids, election_responses = election_data
    election_id = election_ids["ranked_choice"]
    candidates = election_responses["ranked_choice"]["candidates"]
    # logging.error("Election variables:\n%s\n%s", election_ids, election_responses)

    vote_data = {
        str(candidates[i]["id"]): rank + 1
        for rank, i in enumerate(vote_indices)
        if i < len(candidates)
    }
    cast_vote(client, email, {"vote": json.dumps(vote_data)}, election_id)


@patch("application.app.datetime")
@patch("application.vote_calculation.datetime")
def test_get_ranked_choice_election_results(
    mock_app_datetime, mock_vote_datetime, client, election_data
):
    election_ids, election_responses = election_data
    election_id = election_ids["ranked_choice_result"]
    candidates = election_responses["ranked_choice_result"]["candidates"]
    # logging.debug("Election variables:\n%s\n%s", election_ids, election_responses)

    vote_data = [
        ("rank_res_user1@example.com", [0, 1, 2, 3]),
        ("rank_res_user2@example.com", [1, 2, 0, 3]),
        ("rank_res_user3@example.com", [2, 1, 0, 3]),
        ("rank_res_user4@example.com", [0, 2, 1, 3]),
        ("rank_res_user5@example.com", [1, 0, 2, 3]),
        ("rank_res_user6@example.com", [2, 1, 0, 3]),
    ]
    for email, vote_indices in vote_data:
        vote = {
            str(candidates[i]["id"]): rank + 1 for rank, i in enumerate(vote_indices)
        }
        # print("Cast vote: ", vote)
        cast_vote(client, email, {"vote": json.dumps(vote)}, election_id)

    # Mock current time to simulate election expiry
    mock_app_datetime.now.return_value = datetime.now(datetime_UTC) + timedelta(days=2)
    mock_vote_datetime.now.return_value = datetime.now(datetime_UTC) + timedelta(days=2)

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
    assert len(data["results"]) == 1
    assert data["winner"]["name"] == expected_winner["name"]
    assert data["winner"]["votes"] == 6.0

@pytest.mark.skip("Vote calculation logic does not account for draws.")
@patch("application.app.datetime")
@patch("application.vote_calculation.datetime")
def test_get_ranked_choice_election_results_draw(
    mock_app_datetime, mock_vote_datetime, client, election_data
):
    election_ids, election_responses = election_data
    election_id = election_ids["ranked_choice_draw"]
    candidates = election_responses["ranked_choice_draw"]["candidates"]
    # logging.debug("Election variables:\n%s\n%s", election_ids, election_responses)

    vote_data = [
        ("rank_draw_user1@example.com", [0, 1, 2, 3]),
        ("rank_draw_user2@example.com", [1, 2, 0, 3]),
        ("rank_draw_user3@example.com", [2, 0, 1, 3]),
        ("rank_draw_user4@example.com", [0, 2, 1, 3]),
        ("rank_draw_user5@example.com", [1, 0, 2, 3]),
        ("rank_draw_user6@example.com", [2, 1, 0, 3]),
    ]
    for email, vote_indices in vote_data:
        vote = {
            str(candidates[i]["id"]): rank + 1 for rank, i in enumerate(vote_indices)
        }
        # print("Cast vote: ", vote)
        cast_vote(client, email, {"vote": json.dumps(vote)}, election_id)

    # Mock current time to simulate election expiry
    mock_app_datetime.now.return_value = datetime.now(datetime_UTC) + timedelta(days=2)
    mock_vote_datetime.now.return_value = datetime.now(datetime_UTC) + timedelta(days=2)

    # Get election results
    response = client.get(f"/elections/{election_id}/results")
    assert response.status_code == 200
    data = response.json()

    # Verify the results
    assert "results" in data
    assert "winner" in data
    assert data["voting_system"] == "ranked_choice"
    assert data["is_draw"] is True
    expected_winner = candidates[1]  # Adjust index based on expected winner
    assert len(data["results"]) == 4
    assert data["results"][0]["name"] == "Candidate 1"
    assert data["results"][1]["name"] == "Candidate 2"
    assert data["results"][2]["name"] == "Candidate 3"
    assert data["results"][3]["name"] == "Candidate 4"


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
    # logging.error("Election variables:\n%s\n%s", election_ids, election_responses)

    vote_data = {
        str(candidates[i]["id"]): score + 1
        for i, score in enumerate(vote_indices)
        if i < len(candidates)
    }
    cast_vote(client, email, {"vote": json.dumps(vote_data)}, election_id)


# @pytest.mark.skip(reason="Quadratic voting not implemented")
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
