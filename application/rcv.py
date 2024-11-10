import ast
import csv
import pandas as pd

vote_format = [
    '{"11":1, "12":2, "13":3}',
    '{"13":1, "11":2, "12":3}',
    '{"11":1, "13":2, "12":3}',
]


def ranked_choice(vote_format):  # Change parameter to whatever

    list_format = []
    for i in range(len(vote_format)):
        dict_1 = ast.literal_eval(vote_format[i])
        list_format.append(dict((v, k) for k, v in dict_1.items()))
    columns = list_format[0].keys()

    # Define the candidates
    candidates = ["Alice", "Bob", "Charlie", "Diana", "Eve", "Frank", "Grace", "Hank"]
    eliminated_candidates = []

    # Create vote data (each sublist represents a voter's ranked choices)
    votes = []
    num_voters = 1000

    # Write the data to a CSV file
    with open("votes.csv", "w", newline="") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(
            ["voter"] + [f"choice_{i+1}" for i in range(len(columns))]
        )  # len(columns)

        for i in range(len(list_format)):  # list_format
            # Generate unique candidate choices for each voter

            vote_rec = []
            vote_rec.append(f"voter{i+1}")
            for count in range(1, len(columns) + 1):
                vote_rec.append(list_format[i][count])
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

    # Print the winner
    # print(f"Ranked Choice Voting:\nWinner: {rcv_winner}")
    return rcv_winner
