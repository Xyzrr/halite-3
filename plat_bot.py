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


def planned_pos(ship):
    move = planned_moves[ship.id]

    if move is None:
        return ship.position

    return game_map.normalize(ship.position.directional_offset(move))


def resolve_collisions():
    has_collisions = True
    while has_collisions:
        active_positions = defaultdict(set)

        for ship in me.get_ships():
            ppos = planned_pos(ship)
            active_positions[ppos].add(ship)

        has_collisions = False
        for pos, ships in active_positions.items():
            if pos == me.shipyard.position and turns_left < (len(me.get_ships()) / 4 + 2):
                continue
            if len(ships) > 1:
                has_collisions = True
                print_info('{} ships at {}:'.format(len(ships), pos))
                ship_to_move = None
                least_halite_amt = 9999
                for ship in ships:
                    if planned_moves[ship.id] is None:
                        print_info('A ship wants to stay still!')
                        # if one wants to stay still, everyone should stay still
                        ship_to_move = None
                        break

                    # move ship sitting on least halite
                    amt = game_map[ship.position].halite_amount
                    if amt < least_halite_amt:
                        ship_to_move = ship
                        least_halite_amt = amt

                if ship_to_move:
                    if game_map[pos].is_occupied:
                        for ship in me.get_ships():
                            if ship.position == pos:
                                planned = planned_pos(ship)
                                for s in ships:
                                    if s.position == planned:
                                        ship_to_move = s

                for ship in ships:
                    if ship is not ship_to_move:
                        planned_moves[ship.id] = None


def surrounding_halite(pos, radius=None):
    if radius is None:
        radius = game_map.width // 2 - 1
    x, y = pos.x, pos.y
    return halite_matrix.take(range(y - radius, y + radius + 1), axis=0, mode='wrap').take(range(x - radius, x + radius + 1), axis=1, mode='wrap')


def calculate_longterm_halite(ship, pos):
    surroundings = surrounding_halite(pos)
    weighted_sum = np.sum(weight_matrix * surroundings)
    return weighted_sum / 2


def calculate_space_remaining(ship):
    return (constants.MAX_HALITE - ship.halite_amount) / constants.MAX_HALITE


def calculate_dropoff_benefit(ship, pos):
    dist_from_dropoff = game_map.calculate_distance(pos, me.shipyard.position)
    dropoff_benefit = ship.halite_amount * .9**dist_from_dropoff / 2
    return dropoff_benefit


def calculate_urgency_factor(ship, pos):
    dis = game_map.calculate_distance(pos, me.shipyard.position)
    if dis + len(me.get_ships()) / 4 + 2 > turns_left:
        return ship.halite_amount * .9**dis * 100
    return 0


def calculate_neighbor_penalty(ship, pos):
    if len(me.get_ships()) == 1:
        return 0
    if pos == me.shipyard.position:
        return 0
    penalty = 0
    for other in me.get_ships():
        other_pos = planned_pos(other)
        if other.id != ship.id and other.halite_amount >= ship.halite_amount:
            dis = game_map.calculate_distance(other_pos, pos)
            penalty += 400 / (dis + .5)
    penalty /= len(me.get_ships()) - 1
    return penalty


def score_move(ship, dir):
    global debug_indent
    pos = game_map.normalize(ship.position.directional_offset(dir))

    space_remaining = calculate_space_remaining(ship)

    lost_halite = game_map[ship.position].halite_amount * .1
    lost_halite *= space_remaining

    longterm_halite = calculate_longterm_halite(ship, pos)
    longterm_halite *= space_remaining**2

    dropoff_benefit = calculate_dropoff_benefit(ship, pos)

    past_pos_penalty = 0
    if ship.id in past_pos and pos == past_pos[ship.id]:
        past_pos_penalty = 9999

    urgency_factor = calculate_urgency_factor(ship, pos)    

    # print_info("Dir {}".format(dir))
    # debug_indent += 1
    # print_info("Longterm: {}".format(longterm_halite))
    # print_info("Dropoff: {}".format(dropoff_benefit))
    # print_info("Lost: {}".format(lost_halite))
    # print_info("Urgency: {}".format(urgency_factor))
    # debug_indent -= 1

    return longterm_halite + dropoff_benefit - lost_halite - past_pos_penalty + urgency_factor


def score_still(ship):
    global debug_indent
    space_remaining = calculate_space_remaining(ship)

    immediate_halite = game_map[ship.position].halite_amount**2 / 100
    immediate_halite *= space_remaining

    longterm_halite = calculate_longterm_halite(ship, ship.position)
    longterm_halite *= space_remaining**2

    dropoff_benefit = calculate_dropoff_benefit(ship, ship.position)

    on_dropoff = 9999 if ship.position == me.shipyard.position else 0

    need_refuel = 0
    # if (ship.halite_amount < game_map[ship.position].halite_amount * .2):
    #     need_refuel = 20
    if (ship.halite_amount < game_map[ship.position].halite_amount * .1):
        need_refuel = 99999

    urgency_factor = calculate_urgency_factor(ship, ship.position)

    # print_info("Still".format(ship.id))
    # debug_indent += 1
    # print_info("Longterm: {}".format(longterm_halite))
    # print_info("Dropoff: {}".format(dropoff_benefit))
    # print_info("Immediate: {}".format(immediate_halite))
    # print_info("Urgency: {}".format(urgency_factor))
    # debug_indent -= 1

    return immediate_halite + longterm_halite + dropoff_benefit + need_refuel - on_dropoff + urgency_factor


def shipyard_will_be_occupied():
    for ship in me.get_ships():
        if planned_pos(ship) == me.shipyard.position:
            return True
    return False


def build_weight_matrix(radius=None):
    if not radius:
        radius = game_map.width // 2 - 1

    mat = np.zeros((2*radius + 1, 2*radius + 1))
    for x in range(-radius, radius + 1):
        for y in range(-radius, radius + 1):
            dis = np.abs(x) + np.abs(y)
            mat[y + radius, x + radius] = (.9 ** dis) / max(4*dis, 1)
    return mat


def build_halite_matrix():
    mat = np.zeros((game_map.width, game_map.height))
    for x in range(game_map.width):
        for y in range(game_map.height):
            mat[y, x] = game_map[Position(x, y)].halite_amount
    total = np.sum(mat)
    raw = mat
    mat = np.clip(mat, 0, np.average(mat) * 10)
    mat = mat**2 / np.average(mat)
    return mat, raw, total


def dir2move(ship, dir):
    if dir is None:
        return ship.stay_still()
    else:
        return ship.move(dir)


def compute_plans():
    for ship in me.get_ships():
            best_move = None
            best_score = -99999
            for move, score in move_scores[ship.id].items():
                if score > best_score:
                    if move == 'still':
                        best_move = None
                    else:
                        best_move = move
                    best_score = score
            planned_moves[ship.id] = best_move


def compute_scores():
    global debug_indent
    for ship in me.get_ships():
            # print_info("Ship {}".format(ship.id))
            # debug_indent += 1
            for d in Direction.get_all_cardinals():
                move_scores[ship.id][d] = score_move(ship, d)
            move_scores[ship.id]['still'] = score_still(ship)
            # debug_indent -= 1


def adjust_scores():
    for ship in me.get_ships():
        for d in Direction.get_all_cardinals():
            pos = game_map.normalize(ship.position.directional_offset(d))
            move_scores[ship.id][d] -= calculate_neighbor_penalty(ship, pos)
        move_scores[ship.id]['still'] -= calculate_neighbor_penalty(ship, ship.position)


def print_info(s):
    logging.info('\t' * debug_indent + str(s))


def count_total_ships():
    total = 0
    for id, player in game.players.items():
        total += len(player.get_ships())
    return total


def calculate_turns_left():
    if game_map.width == 32:
        total = 401
    elif game_map.width == 40:
        total = 426
    elif game_map.width == 48:
        total = 451
    elif game_map.width == 56:
        total = 476
    else:
        total = 501
    return total - game.turn_number

np.set_printoptions(precision=1)
debug_indent = 0

game = hlt.Game()
me = game.me
game_map = game.game_map

weight_matrix = build_weight_matrix()

game.ready("Plat")

print_info("Successfully created bot! My Player ID is {}.".format(game.my_id))


while True:
    past_pos = {}
    for ship in me.get_ships():
        past_pos[ship.id] = ship.position

    game.update_frame()
    me = game.me
    game_map = game.game_map
    turns_left = calculate_turns_left()
    # print_info(str(turns_left))

    # print_info(str(game.turn_number))

    halite_matrix, raw_halite_matrix, total_halite = build_halite_matrix()
    planned_moves = {}
    move_scores = defaultdict(dict)

    command_queue = []
    
    st = time.process_time()
    compute_scores()
    compute_plans()
    print_info("Computing scores: {}".format(time.process_time() - st))

    st = time.process_time()
    adjust_scores()
    compute_plans()
    print_info("Adjusting scores: {}".format(time.process_time() - st))

    # print_info(str(planned_moves))

    st = time.process_time()
    resolve_collisions()
    print_info("Collisions: {}".format(time.process_time() - st))

    for ship in me.get_ships():
        command_queue.append(dir2move(ship, planned_moves[ship.id]))

    expected_return_per_frame = np.average(raw_halite_matrix) / 12
    new_ship_is_worthwhile = expected_return_per_frame * turns_left > constants.SHIP_COST
    if new_ship_is_worthwhile and me.halite_amount >= constants.SHIP_COST and not shipyard_will_be_occupied():
        command_queue.append(me.shipyard.spawn())

    game.end_turn(command_queue)
