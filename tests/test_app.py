from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from application.app import app, get_db
from application.models import Base, Poll, Option, Vote

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

    vote_response = client.post(
        f"/polls/{poll_id}/vote",
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
