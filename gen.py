#!/usr/bin/env python3
import random
import sys

# Incidents possibles (paire ou valeur seule) avec leur poids
INCIDENTS = [
    ([27, 2], 5),
    ([27, 0], 3),
    ([18, 2], 2),
    ([16, 4], 2),
    ([18, 1], 2),
    ([24], 1),
    ([12, 8], 1),
]

DEBUTS = [
    ([10, 20], 8),
    ([8, 2, 20, 20], 1),
    ([9, 1, 20, 20], 1),
]

REMONTEES = [[20, 20], [10, 20, 30], [10, 20, 20]]
QUEUES = [[10], [20, 10], [10, 10], [9], [0]]


def choix_pondere(options):
    valeurs, poids = zip(*options)
    return list(random.choices(valeurs, weights=poids, k=1)[0])


def gen_sequence():
    while True:
        deltas = choix_pondere(DEBUTS)                    # rampe
        deltas += [30] * random.randint(2, 5)             # plateau

        nb_incidents = random.randint(1, 2)
        for k in range(nb_incidents):
            deltas += choix_pondere(INCIDENTS)            # incident
            deltas += random.choice(REMONTEES)            # remontée
            if k < nb_incidents - 1:
                deltas += [30, 30]

        deltas += random.choice(QUEUES)                   # queue

        longueur = random.randint(12, 15)
        deltas = deltas[:longueur]

        # cumul
        seq, total = [], 0
        for d in deltas:
            total += d
            seq.append(total)

        # contraintes observées dans tes données
        if 12 <= len(seq) <= 15 and 210 <= seq[-1] <= 270:
            return seq


def main():
    if len(sys.argv) > 1:
        n = int(sys.argv[1])
    else:
        n = int(input("Combien de séquences veux-tu générer ? "))

    sequences = [gen_sequence() for _ in range(n)]

    print()
    for s in sequences:
        print(s)

    rep = input("\nSauvegarder dans sequences.txt ? (o/n) ").strip().lower()
    if rep == "o":
        with open("sequences.txt", "w") as f:
            for s in sequences:
                f.write(str(s) + "\n")
        print("Sauvegardé dans sequences.txt")


if __name__ == "__main__":
    main()