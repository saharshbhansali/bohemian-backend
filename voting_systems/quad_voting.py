import csv
import random

# Define the candidates
candidates = ["Alice", "Bob", "Charlie", "Diana", "Eve"]

# Create vote data (each sublist represents a voter's ranked choices)
votes = []
num_voters = 1000

# for _ in range(num_voters):
#     vote = random.sample(candidates, len(candidates))
#     votes.append(vote)

# Write the data to a CSV file
with open('votes.csv', 'w', newline='') as csvfile:
    writer = csv.writer(csvfile)
    writer.writerow(["voter"] + [f"{i}" for i in candidates]) 
    
    for i in range(num_voters):
        list1 = []
        creds = 100
        for j in range(len(candidates)):
            if j == len(candidates) - 1:
                a = creds
            else:
                a = random.randint(0, creds)
            list1.append(a)
            creds -= a

        # Generate unique candidate choices for each voter
        # vote = random.sample(candidates.tolist(), len(candidates))        
        writer.writerow([f"voter {i+1}"] + list1)

import pandas as pd

df = pd.read_csv("votes.csv")
df.head()

sqrt = pd.DataFrame()
for i in candidates:
    sqrt[i] = df[i] ** 0.5
sqrt.head()

n = sqrt.sum()
sqrt_sum = {}
for i in sqrt.columns:
    print(i, " total votes: ", n[i])
    sqrt_sum[i] = n[i]

winner = max(sqrt_sum, key = sqrt_sum.get)

print("Winner is ", winner)