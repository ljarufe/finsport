from bet.constants import TEAM_DIFFERENCE, MIN_PER_TEAM, MIN_PARITY


class Rules(object):

    @classmethod
    def evaluate(cls, local, parity, visitor):
        if not ((abs(local - visitor) > 0) and (
                abs(local - visitor) <= TEAM_DIFFERENCE)):
            return False
        if not (local >= MIN_PER_TEAM) or not (visitor >= MIN_PER_TEAM):
            return False
        if not parity >= MIN_PARITY:
            return False

        return True
