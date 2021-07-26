#!/usr/bin/env python3
# Python 3.6

import hlt
import time
from enum import Enum
from hlt import constants
from hlt.positionals import Direction
from hlt.positionals import Position
import logging
import numpy as np
from collections import defaultdict

np.set_printoptions(precision=1)

game = hlt.Game()
game.ready("funkster")

logging.info("Successfully created bot! My Player ID is {}.".format(game.my_id))


def planned_pos(ship):
    for d in Direction.get_all_cardinals():
        if planned_moves[ship.id] == ship.move(d):
            return game_map.normalize(ship.position.directional_offset(d))
    return ship.position

def resolve_collisions(me, game_map):
    has_collisions = True
    while has_collisions:
        active_positions = defaultdict(set)

        for ship in me.get_ships():
            ppos = planned_pos(ship)
            active_positions[ppos].add(ship)

        has_collisions = False
        for pos, ships in active_positions.items():
            if len(ships) > 1:
                has_collisions = True
                logging.info('{} ships at {}:'.format(len(ships), pos))
                ship_to_move = None
                least_halite_amt = 9999
                for ship in ships:
                    if planned_moves[ship.id] == ship.stay_still():
                        logging.info('A ship wants to stay still!')
                        # if one wants to stay still, everyone should stay still
                        ship_to_move = None
                        break

                    # move ship sitting on least halite
                    amt = game_map[ship.position].halite_amount
                    if amt < least_halite_amt:
                        ship_to_move = ship
                        least_halite_amt = amt

                for ship in ships:
                    if ship is not ship_to_move:
                        planned_moves[ship.id] = ship.stay_still()

def calculate_longterm_halite(ship, dir):
    if dir is Direction.East:
        sub = halite_nparray.take(range(ship.position.x + 1, ship.position.x + game_map.width // 2), mode='wrap', axis=0)
    elif dir is Direction.West:
        sub = halite_nparray.take(range(ship.position.x - game_map.width // 2, ship.position.x - 1), mode='wrap', axis=0)
    elif dir is Direction.South:
        sub = halite_nparray.take(range(ship.position.y + 1, ship.position.y + game_map.height // 2), mode='wrap', axis=1)
    elif dir is Direction.North:
        sub = halite_nparray.take(range(ship.position.y - game_map.height // 2, ship.position.y - 1), mode='wrap', axis=1)
    else:
        sub = halite_nparray

    val = min(np.sum(sub) / sub.size, constants.MAX_HALITE - ship.halite_amount)
    return val * .2

def calculate_neighbor_penalty(ship, pos):
    if len(me.get_ships()) == 1:
        return 0
    penalty = 0
    for other in me.get_ships():
        if other.id != ship.id:
            dis = game_map.calculate_distance(other.position, pos)
            penalty += 100 / (dis + 1)
    penalty /= len(me.get_ships()) - 1
    return penalty

def score_move(ship, dir):
    pos = game_map.normalize(ship.position.directional_offset(dir))
    immediate_halite = min(game_map[pos].halite_amount * .125 - game_map[pos].halite_amount * .05, constants.MAX_HALITE - ship.halite_amount)
    longterm_halite = calculate_longterm_halite(ship, dir)
    dist_from_dropoff = game_map.calculate_distance(pos, me.shipyard.position)
    dropoff_benefit = ship.halite_amount / (dist_from_dropoff + 1)
    neighbor_penalty = calculate_neighbor_penalty(ship, pos)
    logging.info("Dir {} yields {} for ship {}".format(dir, immediate_halite + longterm_halite + dropoff_benefit - neighbor_penalty, ship.id))
    return immediate_halite + longterm_halite + dropoff_benefit - neighbor_penalty

def score_still(ship):
    immediate_halite = min(game_map[ship.position].halite_amount * .25, constants.MAX_HALITE - ship.halite_amount)
    longterm_halite = calculate_longterm_halite(ship, None)
    dist_from_dropoff = game_map.calculate_distance(ship.position, me.shipyard.position)
    on_dropoff = 9999 if dist_from_dropoff == 0 else 0
    dropoff_benefit = ship.halite_amount / (dist_from_dropoff + 1)
    neighbor_penalty = calculate_neighbor_penalty(ship, ship.position)
    need_refuel = 0
    if (ship.halite_amount < game_map[ship.position].halite_amount * .2):
        need_refuel = 20
    if (ship.halite_amount < game_map[ship.position].halite_amount * .1):
        need_refuel = 99999
    logging.info("Still yields {} for ship {}".format(immediate_halite + longterm_halite + dropoff_benefit + need_refuel - neighbor_penalty, ship.id))
    return immediate_halite + longterm_halite + dropoff_benefit + need_refuel - neighbor_penalty - on_dropoff

def shipyard_will_be_occupied():
    for ship in me.get_ships():
        if planned_pos(ship) == me.shipyard.position:
            return True
    return False

while True:
    game.update_frame()
    me = game.me
    game_map = game.game_map
    halite_nparray = np.zeros((game_map.width, game_map.height))
    for x in range(game_map.width):
        for y in range(game_map.height):
            halite_nparray[x, y] = game_map[Position(x, y)].halite_amount

    planned_moves = {}

    command_queue = []

    st = time.process_time()
    for ship in me.get_ships():
        best_move = None
        best_score = -99999
        for d in Direction.get_all_cardinals():
            score = score_move(ship, d)
            if score > best_score:
                best_move = ship.move(d)
                best_score = score
        if score_still(ship) > best_score:
            best_move = ship.stay_still()
        planned_moves[ship.id] = best_move
    logging.info("Picking moves: {}".format(time.process_time() - st))

    st = time.process_time()
    resolve_collisions(me, game_map)
    logging.info("Collisions: {}".format(time.process_time() - st))

    for ship in me.get_ships():
        command_queue.append(planned_moves[ship.id])

    if game.turn_number <= 200 and me.halite_amount >= constants.SHIP_COST and not shipyard_will_be_occupied():
        command_queue.append(me.shipyard.spawn())

    game.end_turn(command_queue)
