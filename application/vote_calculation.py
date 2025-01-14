import logging
import json
from datetime import datetime, timezone, UTC as datetime_UTC
import os
import ast
import csv
import pandas as pd
from sqlalchemy.orm import Session
from .models import Candidate, Vote, AlternativeVote, Election


def ranked_choice(vote_format, candidates):  # Change parameter to whatever
    if not vote_format:
        print("No votes provided to ranked_choice function.")
        return None

    print(f"Vote format: {vote_format}")
    print(f"Candidates: {candidates}")
    vote_list = []
    for i in range(len(vote_format)):
        try:
            vote_dict = ast.literal_eval(vote_format[i])
            vote_list.append(dict((v, k) for k, v in vote_dict.items()))
        except Exception as e:
            print(f"Error parsing vote: {vote_format[i]}, error: {e}")
            continue

    if not vote_list:
        print("No valid votes parsed.")
        return None

    print(vote_list)

    columns = vote_list[0].keys()

    # Define the candidates
    eliminated_candidates = []

    # Create vote data (each sublist represents a voter's ranked choices)
    votes = []
    num_voters = len(vote_list)

    # Write the data to a CSV file
    with open("votes.csv", "w", newline="") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(
            ["voter"] + [f"choice_{i+1}" for i in range(len(columns))]
        )  # len(columns)

        for i in range(len(vote_list)):  # vote_list
            # Generate unique candidate choices for each voter

            vote_rec = []
            vote_rec.append(f"voter{i+1}")
            for count in range(1, len(columns) + 1):
                vote_rec.append(vote_list[i][count])
            writer.writerow(vote_rec)

    # Read the CSV file
    df = pd.read_csv("votes.csv")
    df["current_winner"] = df["choice_1"]
    # Create an array with a list of all the candidates
    candidates = df["current_winner"].unique()
    num_candidates = len(df.columns[1:-1].tolist())

    # Display the dataframe
    # print(df.to_string())

    # Initialize the list of winners
    winners = []
    round_number = 1

    def RankedChoiceVotingRound(df, candidates, round_text, num_candidates):
        # Count the number of first-choice votes for each candidate
        first_choice_votes = df["current_winner"].value_counts()

        total_votes = first_choice_votes.sum()
        round_winner_votes = -1
        round_winner = None
        # Print the results of the current round
        # print(f"{round_text}")
        for candidate, votes in first_choice_votes.items():
            # print(f"{candidate}: {votes} votes")
            if votes > round_winner_votes:
                round_winner_votes = votes
                round_winner = candidate
        # print(f"Total Votes: {total_votes}\n")

        # Identify the candidate with the fewest votes
        min_votes = first_choice_votes.min()
        eliminated_candidate = first_choice_votes[
            first_choice_votes == min_votes
        ].index[0]
        # print(f"Eliminated Candidate: {eliminated_candidate}\nNumber of Votes: {min_votes}\n")

        # Eliminate the candidate with the fewest votes
        candidates = [
            candidate for candidate in candidates if candidate != eliminated_candidate
        ]

        # Redistribute the votes of the eliminated candidate
        def redistribute_votes(row):
            if row["current_winner"] == eliminated_candidate:
                for i in range(1, num_candidates + 1):
                    if row[f"choice_{i}"] in candidates:
                        return row[f"choice_{i}"]
                return None
            return row["current_winner"]

        df["current_winner"] = df.apply(redistribute_votes, axis=1)

        # print(df.to_string() + "\n")

        if len(candidates) == 1:
            return df, candidates, round_winner

        return df, candidates, round_winner

    while len(candidates) > 1:
        df, candidates, rcv_winner = RankedChoiceVotingRound(
            df, candidates, f"Round {round_number}", num_candidates
        )

        round_number += 1

    _, _, _ = RankedChoiceVotingRound(
        df, candidates, f"Round {round_number}", num_candidates
    )

    if os.path.exists("votes.csv"):
        os.remove("votes.csv")

    # Print the winner
    # print(f"Ranked Choice Voting:\nWinner: {rcv_winner}")
    return rcv_winner


def calculate_traditional_votes(election_id: int, db: Session):
    candidate_votes = {
        candidate.id: 0.0
        for candidate in db.query(Candidate)
        .filter(Candidate.election_id == election_id)
        .all()
    }
    votes = (
        db.query(Vote)
        .join(Candidate)
        .filter(Candidate.election_id == election_id)
        .all()
    )
    for vote in votes:
        candidate_votes[vote.candidate_id] += 1.0
    # print(votes)
    # print(candidate_votes)
    return candidate_votes


def calculate_ranked_choice_votes(election_id: int, db: Session, traditional=False):

    candidates = db.query(Candidate).filter(Candidate.election_id == election_id).all()

    # Get all candidates and votes
    votes = (
        db.query(AlternativeVote)
        .filter(AlternativeVote.election_id == election_id)
        .all()
    )

    if traditional:
        candidate_votes = {candidate.id: 0.0 for candidate in candidates}
        for vote in votes:
            print(f"Trad Vote in calc_rcv_votes: {vote.vote.decode()}")
            vote = json.loads(vote.vote.decode())
            candidate_id = int(min(vote, key=vote.get))
            candidate_votes[candidate_id] += 1.0

        # print(votes)
        # print(candidate_votes)
        return candidate_votes

    print(f"RCV Calc Votes: {votes}")

    # return {
    #     candidate.id: 0.0
    #     for candidate in db.query(Candidate)
    #     .filter(Candidate.election_id == election_id)
    #     .all()
    # }

    total_votes = float(len(votes))

    vote_format = [vote.vote.decode() for vote in votes]
    candidate_ids = [str(candidate.id) for candidate in candidates]

    print(f"Vote format: {vote_format}")

    winner = ranked_choice(vote_format, candidate_ids)
    winning_candidate = db.query(Candidate).filter(Candidate.id == winner).first()
    print(
        f"{winner}\nWinner: {winning_candidate.name if winning_candidate else None}, with ID: {winning_candidate.id if winning_candidate else None}\n {winning_candidate}"
    )
    if not winner:
        return {0: total_votes}
    return {int(winner): total_votes}


def calculate_score_votes(election_id: int, db: Session):
    # Implement score voting logic
    pass


def calculate_quadratic_votes(election_id: int, db: Session):
    # Implement quadratic voting logic
    pass
