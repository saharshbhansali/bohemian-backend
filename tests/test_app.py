import logging
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from application.app import app, get_db
from application.models import Base, Poll, Option, Vote, OTP

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

def test_create_poll():
    response = client.post(
        "/polls/",
        json={
            "question": "What's your favorite color?",
            "options": [{"text": "Red"}, {"text": "Blue"}],
        },
    )
    assert response.status_code == 200
    assert response.json()["question"] == "What's your favorite color?"
    assert len(response.json()["options"]) == 2

def test_get_poll():
    response = client.post(
        "/polls/",
        json={
            "question": "What's your favorite color?",
            "options": [{"text": "Red"}, {"text": "Blue"}],
        },
    )
    poll_id = response.json()["id"]
    response = client.get(f"/polls/{poll_id}")
    assert response.status_code == 200
    assert response.json()["question"] == "What's your favorite color?"

def test_vote_on_poll():
    response = client.post(
        "/polls/",
        json={
            "question": "What's your favorite color?",
            "options": [{"text": "Red"}, {"text": "Blue"}],
        },
    )
    poll_id = response.json()["id"]
    option_id = response.json()["options"][0]["id"]

    # Generate OTPs
    client.post("/generate_otps", json={"usernames": ["user1"]})

    # Get OTP for user1
    db = TestingSessionLocal()
    otp_record = db.query(OTP).filter(OTP.username == "user1").first()
    otp = otp_record.otp
    db.close()

    vote_response = client.post(
        f"/polls/{poll_id}/vote?username=user1&otp={otp}",
        json={"option_id": option_id},
    )
    assert vote_response.status_code == 200
    assert vote_response.json() == {"message": "Vote cast successfully"}

def test_delete_poll():
    response = client.post(
        "/polls/",
        json={
            "question": "What's your favorite color?",
            "options": [{"text": "Red"}, {"text": "Blue"}],
        },
    )
    poll_id = response.json()["id"]
    response = client.delete(f"/polls/{poll_id}")
    assert response.status_code == 200
    assert response.json()["message"] == "Poll deleted successfully"
    response = client.get(f"/polls/{poll_id}")
    assert response.status_code == 404

def test_generate_otps():
    response = client.post(
        "/generate_otps", json={"usernames": ["user1", "user2", "user3"]}
    )
    logger.info(f"Request: /generate_otps, Response: {response.json()}")
    assert response.status_code == 200
    assert response.json() == {"message": "OTPs generated successfully"}

    db = TestingSessionLocal()
    otps = db.query(OTP).all()
    assert len(otps) == 3
    db.close()

def test_vote_on_poll_with_valid_otp():
    # Generate OTPs
    response = client.post("/generate_otps", json={"usernames": ["user1"]})
    logger.info(f"Request: /generate_otps, Response: {response.json()}")

    # Create Poll
    response = client.post(
        "/polls/",
        json={
            "question": "What's your favorite color?",
            "options": [{"text": "Red"}, {"text": "Blue"}],
        },
    )
    logger.info(f"Request: /polls/, Response: {response.json()}")
    assert response.status_code == 200
    poll_id = response.json()["id"]
    option_id = response.json()["options"][0]["id"]

    # Get OTP for user1
    db = TestingSessionLocal()
    otp_record = db.query(OTP).filter(OTP.username == "user1").first()
    otp = otp_record.otp
    db.close()

    # Vote with valid OTP
    vote_response = client.post(
        f"/polls/{poll_id}/vote?username=user1&otp={otp}",
        json={"option_id": option_id},
    )
    logger.info(f"Request: /polls/{poll_id}/vote, Response: {vote_response.json()}")
    assert vote_response.status_code == 200
    assert vote_response.json() == {"message": "Vote cast successfully"}

def test_vote_on_poll_with_invalid_otp():
    # Generate OTPs
    response = client.post("/generate_otps", json={"usernames": ["user1"]})
    logger.info(f"Request: /generate_otps, Response: {response.json()}")

    # Create Poll
    response = client.post(
        "/polls/",
        json={
            "question": "What's your favorite color?",
            "options": [{"text": "Red"}, {"text": "Blue"}],
        },
    )
    logger.info(f"Request: /polls/, Response: {response.json()}")
    assert response.status_code == 200
    poll_id = response.json()["id"]
    option_id = response.json()["options"][0]["id"]

    # Vote with invalid OTP
    vote_response = client.post(
        f"/polls/{poll_id}/vote?username=user1&otp=invalid_otp",
        json={"option_id": option_id},
    )
    logger.info(f"Request: /polls/{poll_id}/vote, Response: {vote_response.json()}")
    assert vote_response.status_code == 401
    assert vote_response.json() == {"detail": "Invalid OTP"}

def test_vote_on_poll_with_invalid_username():
    # Generate OTPs
    client.post("/generate_otps", json={"usernames": ["user1"]})

    # Create Poll
    response = client.post(
        "/polls/",
        json={
            "question": "What's your favorite color?",
            "options": [{"text": "Red"}, {"text": "Blue"}],
        },
    )
    poll_id = response.json()["id"]
    option_id = response.json()["options"][0]["id"]

    # Get OTP for user1
    db = TestingSessionLocal()
    otp_record = db.query(OTP).filter(OTP.username == "user1").first()
    otp = otp_record.otp
    db.close()

    # Vote with invalid username
    vote_response = client.post(
        f"/polls/{poll_id}/vote?username=invalid_user&otp={otp}",
        json={"option_id": option_id},
    )
    assert vote_response.status_code == 401
    assert vote_response.json() == {"detail": "Invalid OTP"}
