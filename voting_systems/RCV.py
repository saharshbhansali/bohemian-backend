import pandas as pd
import matplotlib.pyplot as plt


def RankedChoiceVotingRound(df, candidates, round_text, num_candidates):
    # Count the number of first-choice votes for each candidate
    first_choice_votes = df["current_winner"].value_counts()

    total_votes = first_choice_votes.sum()
    round_winner_votes = -1
    round_winner = None
    # Print the results of the current round
    print(f"{round_text}")
    for candidate, votes in first_choice_votes.items():
        print(f"{candidate}: {votes} votes")
        if votes > round_winner_votes:
            round_winner_votes = votes
            round_winner = candidate
    print(f"Total Votes: {total_votes}\n")

    # Create a figure with two subplots
    fig, axs = plt.subplots(1, 2, figsize=(12, 6))

    # Plot pie chart
    axs[0].pie(
        first_choice_votes,
        labels=[
            f"{candidate}\n({votes} votes)"
            for candidate, votes in first_choice_votes.items()
        ],
        autopct="%1.2f%%",
        startangle=140,
    )
    axs[0].set_title(f"{round_text} - Pie Chart")

    # Plot bar chart
    colors = plt.cm.tab20.colors[: len(first_choice_votes)]
    axs[1].bar(first_choice_votes.index, first_choice_votes.values, color=colors)
    axs[1].set_title(f"{round_text} - Bar Chart")
    axs[1].set_xlabel("Candidates")
    axs[1].set_ylabel("Number of Votes")
    axs[1].xaxis.set_major_locator(plt.MaxNLocator(integer=True))

    # Add whitespace between subplots
    fig.subplots_adjust(wspace=0.5)

    # Display the figure
    plt.show()

    # Identify the candidate with the fewest votes
    min_votes = first_choice_votes.min()
    eliminated_candidate = first_choice_votes[first_choice_votes == min_votes].index[0]
    print(
        f"Eliminated Candidate: {eliminated_candidate}\nNumber of Votes: {min_votes}\n"
    )

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


# Traditional Voting
_, _, traditional_winner = RankedChoiceVotingRound(
    df, candidates, f"Traditional Voting", num_candidates
)
candidates = df["choice_1"].unique()
# df["current_winner"] = df["choice_1"]

print(f"Traditional Voting:\nWinner: {traditional_winner}")


# Ranked Choice Voting
while len(candidates) > 1:
    df, candidates, rcv_winner = RankedChoiceVotingRound(
        df, candidates, f"Round {round_number}", num_candidates
    )

    round_number += 1

_, _, _ = RankedChoiceVotingRound(
    df, candidates, f"Round {round_number}", num_candidates
)


# Print the winner
print(f"Ranked Choice Voting:\nWinner: {rcv_winner}")
