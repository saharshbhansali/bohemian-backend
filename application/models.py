import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    DATETIME,
    ForeignKey,
    create_engine,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker

Base = declarative_base()
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

from datetime import datetime

class Election(Base):
    __tablename__ = "elections"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    candidates = relationship("Candidate", back_populates="election")
    end_time = Column(DateTime, nullable=True)

class Candidate(Base):
    __tablename__ = "candidates"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    election_id = Column(Integer, ForeignKey("elections.id"))
    votes = Column(Integer, default=0)
    election = relationship("Election", back_populates="candidates")


class Vote(Base):
    __tablename__ = "votes"
    id = Column(Integer, primary_key=True, index=True)
    candidate_id = Column(Integer, ForeignKey("candidates.id"))
    candidate = relationship("Candidate")


class OTP(Base):
    __tablename__ = "otps"

    id = Column(Integer, primary_key=True, index=True)
    otp = Column(String, index=True)

class ElectionWinner(Base):
    __tablename__ = "election_winners"
    id = Column(Integer, primary_key=True, index=True)
    election_id = Column(Integer, ForeignKey("elections.id"))
    winner_id = Column(Integer, ForeignKey("candidates.id"))
    election = relationship("Election")
    winner = relationship("Candidate")

Base.metadata.create_all(bind=engine)
