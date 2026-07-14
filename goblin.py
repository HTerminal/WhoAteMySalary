# -*- coding: utf-8 -*-
"""The Money Goblin — WhoAteMySalary's little mascot.

It's the creature that (allegedly) ate your salary, so it's the one that reports
new transactions and nags you to categorise them. Pure flavour text — no logic
depends on it, so tweak or add lines freely.
"""
import random

NAME = "The Money Goblin"
EMOJI = "🧌"

# said when a brand-new transaction is detected
_FOUND = [
    "The Money Goblin sniffed out a new receipt.",
    "The Money Goblin caught your money escaping.",
    "The Money Goblin found where some salary went.",
    "Gotcha! The Money Goblin logged a fresh transaction.",
    "The Money Goblin nabbed a receipt from your inbox.",
    "The Money Goblin spotted another nibble out of your salary.",
    "Snack detected — the Money Goblin filed a new transaction.",
]

# said when N transactions are waiting in Review
_REVIEW = [
    "The Money Goblin needs to know what {n} of these were for.",
    "{n} receipt(s) on the Goblin's desk — tell it what they were.",
    "The Money Goblin is squinting at {n} transaction(s). Help it out.",
    "Feed the Money Goblin: {n} transaction(s) need a category.",
]

# said on a single item awaiting review
_ONE = [
    "The Money Goblin wants to know what this was for.",
    "Tell the Money Goblin what this was.",
    "The Money Goblin is curious about this one.",
]

# said when the review queue is empty
_CLEAR = [
    "The Money Goblin is full and happy — nothing to review.",
    "The Money Goblin has nothing to chew on. All caught up!",
    "Clean plate! The Money Goblin is satisfied.",
]


def _pick(seq, **kw):
    return random.choice(seq).format(e=EMOJI, **kw)


def found():
    return f"{EMOJI} {_pick(_FOUND)}"


def review(n):
    return f"{EMOJI} {_pick(_REVIEW, n=n)}"


def one_review():
    return f"{EMOJI} {_pick(_ONE)}"


def all_clear():
    return f"{EMOJI} {_pick(_CLEAR)}"
