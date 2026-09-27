RANKED_ROLE_NAME = "Ranked"

RANK_NAMES = {
    10: {
        "": "| R10 The Divine (#1)",
    },

    9: {
        "High": "| R9 Top One Percent High",
        "Mid": "| R9 Top One Percent Mid",
        "Low": "| R9 Top One Percent Low",
    },

    8: {
        "High": "| R8 Prodigy High",
        "Mid": "| R8 Prodigy Mid",
        "Low": "| R8 Prodigy Low",
    },

    7: {
        "High": "| R7 Master High",
        "Mid": "| R7 Master Mid",
        "Low": "| R7 Master Low",
    },

    6: {
        "High": "| R6 Elite High",
        "Mid": "| R6 Elite Mid",
        "Low": "| R6 Elite Low",
    },

    5: {
        "High": "| R5 Expert High",
        "Mid": "| R5 Expert Mid",
        "Low": "| R5 Expert Low",
    },

    4: {
        "High": "| R4 Advanced High",
        "Mid": "| R4 Advanced Mid",
        "Low": "| R4 Advanced Low",
    },

    3: {
        "High": "| R3 Amateur High",
        "Mid": "| R3 Amateur Mid",
        "Low": "| R3 Amateur Low",
    },

    2: {
        "High": "| R2 Rookie High",
        "Mid": "| R2 Rookie Mid",
        "Low": "| R2 Rookie Low",
    },

    1: {
        "High": "| R1 Noob High",
        "Mid": "| R1 Noob Mid",
        "Low": "| R1 Noob Low",
    },
}




SUBRANK_VALUE = {
    "Low": 0,
    "Mid": 1,
    "High": 2,
}



def get_rank_from_member(member):
    """
    Finds the player's R1-R10 Discord role.

    Returns:
        (rank_number, subrank, exact_role_name)

    Example:
        (5, "Mid", "| R5 Expert Mid")

    Returns None if the player has no R1-R10 role.
    """

    role_names = {
        role.name
        for role in member.roles
    }

    for rank in range(10, 0, -1):

        for subrank, role_name in RANK_NAMES[rank].items():

            if role_name in role_names:

                return (
                    rank,
                    subrank,
                    role_name,
                )

    return None



def is_ranked(member):
    """
    Player must have:

    1. Ranked role
    2. R1-R10 role
    """

    role_names = {
        role.name
        for role in member.roles
    }

    if RANKED_ROLE_NAME not in role_names:
        return False

    return get_rank_from_member(member) is not None



def format_member_rank(member):
    """
    Returns the exact Discord rank role name.
    """

    result = get_rank_from_member(member)

    if result is None:
        return "Unranked"

    return result[2]



def rank_score(rank, subrank):
    """
    Converts a rank into a number for matchmaking.

    Higher number = higher rank.
    """

    return (
        rank * 3
        + SUBRANK_VALUE.get(subrank, 0)
    )


def matchmaking_distance(
    rank1,
    subrank1,
    rank2,
    subrank2,
):

    return abs(
        rank_score(
            rank1,
            subrank1,
        )
        -
        rank_score(
            rank2,
            subrank2,
        )
    )



def best_role_match(
    player,
    candidates,
):

    if not candidates:
        return None

    return min(
        candidates,
        key=lambda p:
            matchmaking_distance(
                player["rank"],
                player["subrank"],
                p["rank"],
                p["subrank"],
            ),
    )



BANDS = [
    (0, "Unranked"),
    (800, "Bronze"),
    (1000, "Silver"),
    (1200, "Gold"),
    (1400, "Platinum"),
    (1600, "Diamond"),
    (1800, "Champion"),
    (2000, "Elite"),
]


def elo_to_rank(elo):

    if elo >= 2000:
        return "Elite", ""

    if elo >= 1800:
        return "Champion", "I"

    if elo >= 1600:
        return "Diamond", "I"

    if elo >= 1400:
        return "Platinum", "I"

    if elo >= 1200:
        return "Gold", "I"

    if elo >= 1000:
        return "Silver", "I"

    if elo >= 800:
        return "Bronze", "I"

    return "Unranked", ""


def format_rank(elo):

    rank, subrank = elo_to_rank(elo)

    if subrank:
        return f"{rank} {subrank}"

    return rank


def expected_score(
    player_elo,
    opponent_elo,
):

    return 1 / (
        1
        +
        10 ** (
            (opponent_elo - player_elo)
            / 400
        )
    )


def new_elo(
    winner_elo,
    loser_elo,
):

    winner_expected = expected_score(
        winner_elo,
        loser_elo,
    )

    loser_expected = expected_score(
        loser_elo,
        winner_elo,
    )

    winner_new = round(
        winner_elo
        + 32 * (1 - winner_expected)
    )

    loser_new = round(
        loser_elo
        + 32 * (0 - loser_expected)
    )

    return (
        max(0, winner_new),
        max(0, loser_new),
    )


def best_match(
    player_elo,
    candidates,
):

    if not candidates:
        return None

    return min(
        candidates,
        key=lambda player:
            abs(
                player["elo"]
                - player_elo
            ),
    )
