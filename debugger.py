import logging
from hlt.positionals import Direction


class Debugger:
    DEBUG = 1

    def __init__(self):
        self.indent = 0

    def log(self, s):
        logging.info('\t' * self.indent + str(s))

    def print_ship_statuses(self, ships, move_scores):
        for ship in sorted(ships, key=lambda s: s.id):
            self.print_ship_status(ship, move_scores)

    def print_ship_status(self, ship, move_scores):
        self.log("Ship {}:".format(ship.id))
        self.indent += 1
        self.print_move_scores(ship, move_scores)
        self.indent -= 1

    def print_move_scores(self, ship, move_scores, interests=['immediate', 'longterm', 'neighbor', 'dropoff', 'enemy', 'inspiration']):
        if self.DEBUG == 0:
            return

        if len(move_scores[ship.id]) == 0:
            return

        scores = {ok: {k: int(v) for k, v in ov.items()} for ok, ov in move_scores[ship.id].items()}
        total_scores = {k: sum(v.values()) for k, v in scores.items()}
        s = "       {:>7}         ".format(total_scores[Direction.North])
        for interest in interests:
            s += "       {:>7}       ".format(scores[Direction.North][interest])
        self.log(s)

        s = "{:>7}{:>7}{:>7}  ".format(total_scores[Direction.West], total_scores[Direction.Still], total_scores[Direction.East])
        for interest in interests:
            s += "{:>7}{:>7}{:>7}".format(scores[Direction.West][interest], scores[Direction.Still][interest], scores[Direction.East][interest])
        self.log(s)

        s = "       {:>7}         ".format(total_scores[Direction.South])
        for interest in interests:
            s += ("       {:>7}       ".format(scores[Direction.South][interest]))
        self.log(s)