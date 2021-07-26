#!/usr/bin/env python3
# Python 3.6

import hlt
from enum import Enum
from hlt import constants
from hlt.positionals import Direction
from hlt.positionals import Position
import logging
import numpy as np
from collections import defaultdict

np.set_printoptions(precision=1)

game = hlt.Game()
game.ready("Two-bot")

logging.info("Successfully created bot! My Player ID is {}.".format(game.my_id))


def find_new_target(game, ship_targets, ship):
    game_map = game.game_map
    cell_values = np.zeros((game_map.width, game_map.height))
    spos = game.me.shipyard.position

    for i in range(game_map.width):
        for j in range(game_map.height):
            pos = Position(i, j)
            dis = game_map.calculate_distance(ship.position, pos)
            sdis = game_map.calculate_distance(spos, pos)
            raw_value = game_map[pos].halite_amount / (dis + 1 + sdis)
            if i == ship.position.x and j == ship.position.y:
                raw_value += game_map[ship.position].halite_amount * .25
            cell_values[i, j] = min(raw_value, constants.MAX_HALITE - ship.halite_amount)

    dis = game_map.calculate_distance(ship.position, spos)
    cell_values[spos.x, spos.y] += ship.halite_amount / (dis + 1)

    # avoid other ships' targets
    # for target in ship_targets.values():
    #     cell_values[target.x, target.y] -= 200
    #     for d in Direction.get_all_cardinals():
    #         newpos = game_map.normalize(target.directional_offset(d))
    #         cell_values[newpos.x, newpos.y] -= 100

    if ship.halite_amount < game_map[ship.position].halite_amount * .1:
        cell_values[ship.position.x, ship.position.y] = 9999
    best_pos = np.unravel_index(cell_values.argmax(), cell_values.shape)
    logging.info("Ship {}'s best value is {}".format(ship.id, cell_values[best_pos[0], best_pos[1]]))
    logging.info("Ship {}'s shipyard value is {}".format(ship.id, cell_values[spos.x, spos.y]))
    return Position(best_pos[0], best_pos[1])

def initialize_ship(ship):
    ship_states[ship.id] = {
        'target': find_new_target(ship)
    }


def planned_pos(game_map, planned_moves, ship):
    for d in Direction.get_all_cardinals():
        if planned_moves[ship.id] == ship.move(d):
            return game_map.normalize(ship.position.directional_offset(d))
    return ship.position

def resolve_collisions(me, game_map, planned_moves):
    has_collisions = True
    while has_collisions:
        active_positions = defaultdict(set)

        for ship in me.get_ships():
            ppos = planned_pos(game_map, planned_moves, ship)
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

while True:
    game.update_frame()
    me = game.me
    game_map = game.game_map

    planned_moves = {}
    ship_targets = {}

    command_queue = []

    sorted_ships = sorted(me.get_ships(), key=lambda a: a.id)
    for ship in sorted_ships:
        ship_targets[ship.id] = find_new_target(game, ship_targets, ship)

        bestmove = None
        bestdis = 9999
        bestnewpos = None
        for d in Direction.get_all_cardinals() + [None]:
            if d is None:
                newpos = ship.position
            else:
                newpos = game_map.normalize(ship.position.directional_offset(d))
            dis = game_map.calculate_distance(newpos, ship_targets[ship.id])
            if dis < bestdis:
                bestdis = dis
                bestmove = ship.stay_still() if d is None else ship.move(d)
                bestnewpos = newpos
        planned_moves[ship.id] = bestmove

    logging.info(ship_targets)
    resolve_collisions(me, game_map, planned_moves)

    for ship in me.get_ships():
        command_queue.append(planned_moves[ship.id])

    if len(me.get_ships()) < 2 and game.turn_number <= 200 and me.halite_amount >= constants.SHIP_COST and not game_map[me.shipyard].is_occupied:
        command_queue.append(me.shipyard.spawn())

    game.end_turn(command_queue)
