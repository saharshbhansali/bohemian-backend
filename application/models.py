import os
from dotenv import load_dotenv
from sqlalchemy import (
    Column,
    Integer,
    Float,
    String,
    BLOB,
    DateTime,
    Enum,
    ForeignKey,
    create_engine,
)
from sqlalchemy.orm import relationship, sessionmaker, declarative_base
from datetime import datetime


load_dotenv()

# Determine if running in a test environment
TESTING = os.getenv("TESTING") == "1"

if TESTING:
    # Use the same test database as in tests/test_app.py
    DATABASE_URL = "sqlite:///./test.db"
else:
    DATABASE_URL = os.getenv("DATABASE_URL")

Base = declarative_base()
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Election(Base):
    __tablename__ = "elections"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    voting_system = Column(
        Enum(
            "traditional",
            "ranked_choice",
            "score_voting",
            "quadratic_voting",
            name="voting_system_options",
        ),
        default="traditional",
    )
    end_time = Column(DateTime, nullable=True)
    candidates = relationship("Candidate", back_populates="election")


class Candidate(Base):
    __tablename__ = "candidates"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    election_id = Column(Integer, ForeignKey("elections.id"))
    votes = Column(Integer, default=0, nullable=False)
    election = relationship("Election", back_populates="candidates")


class Vote(Base):
    __tablename__ = "votes"
    id = Column(Integer, primary_key=True, index=True)
    validation_token = Column(String, index=True, nullable=False)
    election_id = Column(Integer, ForeignKey("elections.id"))
    candidate_id = Column(Integer, ForeignKey("candidates.id"))
    election = relationship("Election")
    candidate = relationship("Candidate")


class AlternativeVote(Base):
    __tablename__ = "alternative_votes"
    id = Column(Integer, primary_key=True, index=True)
    validation_token = Column(String, index=True, nullable=False)
    election_id = Column(Integer, ForeignKey("elections.id"))
    vote_string = Column(String, index=True, default="")
    vote = Column(BLOB, index=True)
    election = relationship("Election")


class OTP(Base):
    __tablename__ = "otps"
    id = Column(Integer, primary_key=True, index=True)
    otp = Column(String, index=True)


class ElectionWinner(Base):
    __tablename__ = "election_winners"
    id = Column(Integer, primary_key=True, index=True)
    election_id = Column(Integer, ForeignKey("elections.id"))
    winner_id = Column(Integer, ForeignKey("candidates.id"))
    votes = Column(Float, default=0, nullable=False)
    election = relationship("Election")
    winner = relationship("Candidate")


if not TESTING:
    Base.metadata.create_all(bind=engine)
