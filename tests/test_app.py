from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from application.app import app, get_db
from application.models import Base, Election, Candidate, OTP
from application.utils import generate_otp, hash_email_otp
from datetime import datetime, timedelta, UTC as datetime_UTC
from unittest.mock import patch
import csv

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


def cast_vote(email, option, election_id):
    otp = get_otp_from_csv(email)
    if otp is None:
        raise ValueError(f"OTP for {email} not found in identities.csv")

    hashed_otp = hash_email_otp(email, otp)

    # Cast vote
    response = client.post(
        f"/elections/{election_id}/vote",
        headers={"Authorization": f"Bearer {hashed_otp}"},
        json={"option_id": option},
    )

    assert response.status_code == 200
    assert response.json() == {"message": "Vote cast successfully"}


def test_generate_otps():
    response = client.post(
        "/generate_otps",
        json={
            "usernames": ["user1@example.com", "user2@example.com", "user3@example.com"]
        },
    )
    assert response.status_code == 200
    assert response.json() == {"message": "OTPs generated and stored successfully"}


def test_create_election():
    test_generate_otps()
    response = client.post(
        "/elections/",
        json={
            "title": "Test Election",
            "candidates": [{"name": "Candidate 1"}, {"name": "Candidate 2"}],
            "end_time": (datetime.now(datetime_UTC) + timedelta(days=1)).isoformat(),
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Test Election"
    assert len(data["candidates"]) == 2
    assert data["candidates"][0]["name"] == "Candidate 1"
    assert data["candidates"][1]["name"] == "Candidate 2"

    return response


def test_vote_in_election():
    response = test_create_election()
    election_id = response.json()["id"]
    candidates = response.json()["candidates"]

    cast_vote("user1@example.com", candidates[0]["id"], election_id)
    cast_vote("user2@example.com", candidates[1]["id"], election_id)
    cast_vote("user3@example.com", candidates[0]["id"], election_id)

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

    cast_vote("user1@example.com", candidates[0]["id"], election_id)
    cast_vote("user2@example.com", candidates[1]["id"], election_id)

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
