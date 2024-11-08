from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from application.app import app, get_db
from application.models import Base, Election, Candidate, OTP

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


def test_generate_otps():
    response = client.post("/generate_otps", json={"usernames": ["user1", "user2"]})
    assert response.status_code == 200
    assert response.json() == {"message": "OTPs generated successfully"}


def test_create_election():
    test_generate_otps()
    response = client.post(
        "/elections/",
        json={
            "title": "Test Election",
            "candidates": [{"name": "Candidate 1"}, {"name": "Candidate 2"}],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Test Election"
    assert len(data["candidates"]) == 2
    assert data["candidates"][0]["name"] == "Candidate 1"
    assert data["candidates"][1]["name"] == "Candidate 2"


def test_vote_in_election():
    # Generate OTP for user
    # client.post("/generate_otps", json={"usernames": ["user1"]})

    test_create_election()

    db = TestingSessionLocal()

    otp = db.query(OTP).filter(OTP.username == "user1").first().otp
    db.close()

    # Cast vote
    response = client.post(
        "/elections/1/vote",
        params={"username": "user1", "otp": otp},
        json={"option_id": 1},
    )

    assert response.status_code == 200
    assert response.json() == {"message": "Vote cast successfully"}

    otp = db.query(OTP).filter(OTP.username == "user2").first().otp
    db.close()

    # Cast vote
    response = client.post(
        "/elections/1/vote",
        params={"username": "user2", "otp": otp},
        json={"option_id": 2},
    )

    assert response.status_code == 200
    assert response.json() == {"message": "Vote cast successfully"}


def test_get_election_results():

    test_vote_in_election()

    response = client.get("/elections/1/results")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["name"] == "Candidate 1"
    assert data[1]["name"] == "Candidate 2"
