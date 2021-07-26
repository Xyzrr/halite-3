#!/usr/bin/env python3
# Python 3.6

import hlt
import time
from enum import Enum
from hlt import constants
from hlt.positionals import Direction
from hlt.positionals import Position
from hlt.entity import Dropoff
import logging
import numpy as np
from collections import defaultdict
from debugger import Debugger
from hlt.commands import *


def count_total_ships():
    total = 0
    for id, player in game.players.items():
        total += len(player.get_ships())
    return total

def turns_left():
    return constants.MAX_TURNS - game.turn_number

def dist_from_dropoff(pos):
    shortest = 999
    for dropoff in me.get_dropoffs() + [me.shipyard]:
        dis = game_map.calculate_distance(pos, dropoff.position)
        shortest = min(shortest, dis)
    return shortest

def on_dropoff(pos):
    for dropoff in me.get_dropoffs() + [me.shipyard]:
        if dropoff.position == pos:
            return True
    return False


def get_surroundings(matrix, pos, radius):
    x, y = pos.x, pos.y
    return matrix.take(range(y - radius, y + radius + 1), axis=0, mode='wrap').take(range(x - radius, x + radius + 1), axis=1, mode='wrap')

def surrounding_halite(pos, radius=None):
    if radius is None:
        radius = game_map.width // 2 - 1
    return get_surroundings(halite_matrix, pos, radius)

def surrounding_neighbors(pos, radius=4):
    return get_surroundings(neighbor_matrix, pos, radius)

def surrounding_enemies(pos, radius=1):
    return get_surroundings(enemy_matrix, pos, radius)


def calculate_longterm_halite(ship, pos):
    if immune_timer[ship.id] > 0:
        return 0

    surroundings = surrounding_halite(pos)
    clipped = np.clip(surroundings*.75, 0, constants.MAX_HALITE - ship.halite_amount)
    modified = np.clip(clipped - surroundings * .1, 0, None)
    modified = clipped**2 / average_halite
    weighted_sum = np.sum(weight_matrix * modified)
    score = weighted_sum / 4
    return score

def calculate_space_remaining(ship):
    return (constants.MAX_HALITE - ship.halite_amount) / constants.MAX_HALITE

def calculate_dropoff_benefit(ship, pos):
    dis = dist_from_dropoff(pos)
    turns_needed = dis + len(me.get_ships()) / 4 + 2

    # if turns_needed <= turns_left() < turns_needed + game_map.width /2 + ((constants.MAX_HALITE - ship.halite_amount) /(average_halite / 12)):
    #     return 0

    dropoff_benefit = ship.halite_amount * .9**dis / 2
    return dropoff_benefit

def calculate_urgency_factor(ship, pos):
    dis = dist_from_dropoff(pos)
    turns_needed = dis + len(me.get_ships()) / 4 + 2

    if turns_needed > turns_left():
        return ship.halite_amount * .9**dis * 100

    return 0

def calculate_neighbor_penalty(ship, pos):
    # if pos == me.shipyard.position:
    #     return 0
    surroundings = surrounding_neighbors(pos)
    weighted_sum = np.sum(neighbor_weight_matrix * surroundings)

    # debug.log(surroundings)
    # debug.log("Ship {} Pos {} Penalty {}".format(ship.id, pos, weighted_sum * 150))

    return weighted_sum * average_halite

def calculate_immediate_halite(ship, dir, pos):
    if dir is Direction.Still:
        percent_collected = .75 if is_inspired(ship) else .25
        return min(game_map[ship.position].halite_amount * percent_collected, constants.MAX_HALITE - ship.halite_amount)**2 / (average_halite/8)

    space_remaining = calculate_space_remaining(ship)
    penalty = game_map[ship.position].halite_amount * .1
    penalty *= space_remaining    
    return -penalty
    

def calculate_past_position_penalty(ship, pos):
    penalty = 0
    if ship.id in past_pos and pos == past_pos[ship.id] and not on_dropoff(ship.position):
        penalty = 9999
    return penalty

def calculate_need_refuel(ship):
    score = 0
    # if (ship.halite_amount < game_map[ship.position].halite_amount * .2):
    #     score = 20
    if (ship.halite_amount < game_map[ship.position].halite_amount * .1):
        score = 99999
    return score

def is_inspired(ship):
    surroundings = surrounding_enemies(ship.position, radius=4)
    return np.sum(surroundings * inspired_weight_matrix) >= 2

def calculate_inspiration_bonus(ship, pos):
    if len(game.players) == 2:
        return 0
    if immune_timer[ship.id] > 0:
        return 0
    surroundings = surrounding_enemies(pos, radius=5)
    weighted_sum = np.sum(inspiration_weight_matrix * surroundings)
    return weighted_sum * average_halite / 4 * max(calculate_space_remaining(ship) - .2, 0)

def calculate_enemy_penalty(ship, pos):
    surroundings = surrounding_enemies(pos, radius=1)
    weighted_sum = np.sum(enemy_weight_matrix * surroundings)
    if len(game.players) == 2:
        return weighted_sum * max(0, ship.halite_amount - 300) / 4
    else:
        return weighted_sum * average_halite * (1 + ship.halite_amount / constants.MAX_HALITE) * 30


def score_move(ship, dir):
    pos = game_map.normalize(ship.position.directional_offset(dir))
    score = move_scores[ship.id][dir]

    score['immediate'] = calculate_immediate_halite(ship, dir, pos)
    score['longterm'] = calculate_longterm_halite(ship, pos)
    score['dropoff'] = calculate_dropoff_benefit(ship, pos)
    score['urgent'] = calculate_urgency_factor(ship, pos)
    score['neighbor'] = -calculate_neighbor_penalty(ship, pos)
    score['inspiration'] = calculate_inspiration_bonus(ship, pos)
    score['enemy'] = -calculate_enemy_penalty(ship, pos)
    if dir is Direction.Still:
        score['refuel'] = calculate_need_refuel(ship)
        score['on_dropoff'] = -9999 if on_dropoff(ship.position) else 0
    else:
        score['pastpos'] = -calculate_past_position_penalty(ship, pos)

def should_convert_to_dropoff(ship):
    halite_required = 4000 - ship.halite_amount - game_map[ship.position].halite_amount
    dist = dist_from_dropoff(ship.position)
    weighted_sum = np.sum(dropoff_weight_matrix * surrounding_halite(ship.position, radius=6))
    if weighted_sum * (min(dist, 14))**2 / 600 > halite_required:
        if me.halite_amount >= halite_required:
            me.halite_amount -= halite_required
            me._dropoffs[999] = Dropoff(me.id, 999, ship.position)
            return True
        else:
            save_for_dropoff = True
    return False

def build_weight_matrix(radius=None, discount_rate=.9, center=1):
    if not radius:
        radius = game_map.width // 2 - 1

    mat = np.zeros((2*radius + 1, 2*radius + 1))
    for x in range(-radius, radius + 1):
        for y in range(-radius, radius + 1):
            dis = np.abs(x) + np.abs(y)
            mat[y + radius, x + radius] = ((discount_rate ** dis) / (4*dis)) if dis > 0 else center
    return mat

def build_halite_matrix():
    mat = np.zeros((game_map.width, game_map.height))
    for x in range(game_map.width):
        for y in range(game_map.height):
            mat[y, x] = game_map[Position(x, y)].halite_amount
    return mat

def build_enemy_matrix():
    mat = np.zeros((game_map.width, game_map.height))
    for id, player in game.players.items():
        if player != me:
            for ship in player.get_ships():
                pos = ship.position
                mat[pos.y, pos.x] = 1
    return mat


def compute_plan(ship):
    best_move = None
    best_score = -99999
    for move, score in move_scores[ship.id].items():
        total_score = sum(score.values())
        if total_score > best_score:
            best_move = move
            best_score = total_score
    return best_move

def planned_pos(ship):
    if planned_moves[ship.id] == CONSTRUCT:
        return None

    return game_map.normalize(ship.position.directional_offset(planned_moves[ship.id]))


def compute_scores():
    for ship in sorted(me.get_ships(), key=lambda s:(s.halite_amount, dist_from_dropoff(s.position)), reverse=True):
        if ship.id in planned_moves and planned_moves[ship.id] == CONSTRUCT:
            continue

        for d in Direction.get_all_cardinals() + [Direction.Still]:
            score_move(ship, d)
        planned_moves[ship.id] = compute_plan(ship)

        ppos = planned_pos(ship)
        if ppos is not None:
            neighbor_matrix[ppos.y, ppos.x] = 1


def resolve_collisions():   
    def find_active_positions():
        active_positions = defaultdict(set)

        for ship in me.get_ships():
            ppos = planned_pos(ship)
            if ppos is not None:
                active_positions[ppos].add(ship)

        return active_positions 

    has_collisions = True
    while has_collisions:
        active_positions = find_active_positions()

        has_collisions = False
        for pos, ships in active_positions.items():
            if on_dropoff(pos) and turns_left() < (len(me.get_ships()) / 4 + 2):
                continue
            if len(ships) > 1:
                has_collisions = True
                # print_info('{} ships at {}:'.format(len(ships), pos))
                ship_to_move = None
                least_halite_amt = 9999
                for ship in ships:
                    if planned_moves[ship.id] is Direction.Still:
                        # print_info('A ship wants to stay still!')
                        # if one wants to stay still, everyone should stay still
                        ship_to_move = None
                        break

                    # move ship sitting on least halite
                    amt = game_map[ship.position].halite_amount
                    if amt < least_halite_amt:
                        ship_to_move = ship
                        least_halite_amt = amt

                if ship_to_move:
                    if game_map[pos].is_occupied and game_map[pos].ship.owner == me.id:
                        planned = planned_pos(game_map[pos].ship)
                        if planned:
                            ship_to_move = game_map[planned].ship

                for ship in ships:
                    if ship is not ship_to_move:
                        planned_moves[ship.id] = Direction.Still

def consider_spawning():
    if save_for_dropoff:
        return

    def shipyard_will_be_occupied():
        for ship in me.get_ships():
            ppos = planned_pos(ship)
            if ppos is not None and ppos == me.shipyard.position:
                return True
        return False

    expected_return_per_frame = average_halite / (8 + count_total_ships()/10)
    new_ship_is_worthwhile = expected_return_per_frame * turns_left() > constants.SHIP_COST
    if new_ship_is_worthwhile and me.halite_amount >= constants.SHIP_COST and not shipyard_will_be_occupied():
        command_queue.append(me.shipyard.spawn())

def manage_immune_timer():
    for ship in me.get_ships():
        if ship.halite_amount == constants.MAX_HALITE:
            immune_timer[ship.id] = 5
        elif on_dropoff(ship.position) :
            immune_timer[ship.id] = 0
        else:
            immune_timer[ship.id] = max(0, immune_timer[ship.id] - 1)


np.set_printoptions(precision=1)
debug = Debugger()

game = hlt.Game()
me = game.me
game_map = game.game_map

weight_matrix = build_weight_matrix()
neighbor_weight_matrix = build_weight_matrix(radius=4, center=5)
inspiration_weight_matrix = np.array([
    [0   , 0   , 0   , 0   , 0   , 0.1 , 0   , 0   , 0   , 0   , 0   ],
    [0   , 0   , 0   , 0   , 0.1 , 0.25, 0.1 , 0   , 0   , 0   , 0   ],
    [0   , 0   , 0   , 0.1 , 0.25, 0.5 , 0.25, 0.1 , 0   , 0   , 0   ],
    [0   , 0   , 0.1 , 0.25, 0.5 , 1   , 0.5 , 0.25, 0.1 , 0   , 0   ],
    [0   , 0.1 , 0.25, 0.5 , 1   , 0   , 1   , 0.5 , 0.25, 0.1 , 0   ],
    [0.1 , 0.25, 0.5 , 1   , 0   , 0   , 0   , 1   , 0.5 , 0.25, 0.1 ],
    [0   , 0.1 , 0.25, 0.5 , 1   , 0   , 1   , 0.5 , 0.25, 0.1 , 0   ],
    [0   , 0   , 0.1 , 0.25, 0.5 , 1   , 0.5 , 0.25, 0.1 , 0   , 0   ],
    [0   , 0   , 0   , 0.1 , 0.25, 0.5 , 0.25, 0.1 , 0   , 0   , 0   ],
    [0   , 0   , 0   , 0   , 0.1 , 0.25, 0.1 , 0   , 0   , 0   , 0   ],
    [0   , 0   , 0   , 0   , 0   , 0.1 , 0   , 0   , 0   , 0   , 0   ],
])
inspired_weight_matrix = np.array([
    [0   , 0   , 0   , 0   , 1   , 0   , 0   , 0   , 0   ],
    [0   , 0   , 0   , 1   , 1   , 1   , 0   , 0   , 0   ],
    [0   , 0   , 1   , 1   , 1   , 1   , 1   , 0   , 0   ],
    [0   , 1   , 1   , 1   , 1   , 1   , 1   , 1   , 0   ],
    [1   , 1   , 1   , 1   , 1   , 1   , 1   , 1   , 1   ],
    [0   , 1   , 1   , 1   , 1   , 1   , 1   , 1   , 0   ],
    [0   , 0   , 1   , 1   , 1   , 1   , 1   , 0   , 0   ],
    [0   , 0   , 0   , 1   , 1   , 1   , 0   , 0   , 0   ],
    [0   , 0   , 0   , 0   , 1   , 0   , 0   , 0   , 0   ]
])
enemy_weight_matrix = np.array([
    [0   , 1   , 0   ],
    [1   , 1   , 1   ],
    [0   , 1   , 0   ]
])
dropoff_weight_matrix = np.array([
    [0   , 0   , 0   , 0   , 0.1 , 0.2 , 0.3 , 0.2 , 0.1 , 0   , 0   , 0   , 0   ],
    [0   , 0   , 0   , 0.1 , 0.2 , 0.3 , 0.4 , 0.3 , 0.2 , 0.1 , 0   , 0   , 0   ],
    [0   , 0   , 0.1 , 0.2 , 0.3 , 0.4 , 0.5 , 0.4 , 0.3 , 0.2 , 0.1 , 0   , 0   ],
    [0   , 0.1 , 0.2 , 0.3 , 0.4 , 0.5 , 0.6 , 0.5 , 0.4 , 0.3 , 0.2 , 0.1 , 0   ],
    [0.1 , 0.2 , 0.3 , 0.4 , 0.5 , 0.6 , 0.7 , 0.6 , 0.5 , 0.4 , 0.3 , 0.2 , 0.1 ],
    [0.2 , 0.3 , 0.4 , 0.5 , 0.6 , 0.7 , 0.9 , 0.7 , 0.6 , 0.5 , 0.4 , 0.3 , 0.2 ],
    [0.3 , 0.4 , 0.5 , 0.6 , 0.7 , 0.9 , 1   , 0.9 , 0.7 , 0.6 , 0.5 , 0.4 , 0.3 ],
    [0.2 , 0.3 , 0.4 , 0.5 , 0.6 , 0.7 , 0.9 , 0.7 , 0.6 , 0.5 , 0.4 , 0.3 , 0.2 ],
    [0.1 , 0.2 , 0.3 , 0.4 , 0.5 , 0.6 , 0.7 , 0.6 , 0.5 , 0.4 , 0.3 , 0.2 , 0.1 ],
    [0   , 0.1 , 0.2 , 0.3 , 0.4 , 0.5 , 0.6 , 0.5 , 0.4 , 0.3 , 0.2 , 0.1 , 0   ],
    [0   , 0   , 0.1 , 0.2 , 0.3 , 0.4 , 0.5 , 0.4 , 0.3 , 0.2 , 0.1 , 0   , 0   ],
    [0   , 0   , 0   , 0.1 , 0.2 , 0.3 , 0.4 , 0.3 , 0.2 , 0.1 , 0   , 0   , 0   ],
    [0   , 0   , 0   , 0   , 0.1 , 0.2 , 0.3 , 0.2 , 0.1 , 0   , 0   , 0   , 0   ]
])

immune_timer = defaultdict(int)

game.ready("Xyzrr")


while True:
    past_pos = {}
    for ship in me.get_ships():
        past_pos[ship.id] = ship.position

    game.update_frame()
    me = game.me
    game_map = game.game_map

    halite_matrix = build_halite_matrix()
    neighbor_matrix = np.zeros((game_map.height, game_map.width))
    enemy_matrix = build_enemy_matrix()
    total_halite = np.sum(halite_matrix)
    average_halite = total_halite/game_map.width**2
    planned_moves = {}
    move_scores = defaultdict(lambda: defaultdict(dict))
    manage_immune_timer()

    command_queue = []

    save_for_dropoff = False
    for ship in sorted(me.get_ships(), key=lambda s:s.halite_amount + game_map[s.position].halite_amount, reverse=True):
        if should_convert_to_dropoff(ship):
            planned_moves[ship.id] = CONSTRUCT
    
    st = time.process_time()
    compute_scores()
    debug.log("Computing scores: {}".format(time.process_time() - st))

    debug.print_ship_statuses(me.get_ships(), move_scores)

    st = time.process_time()
    resolve_collisions()
    debug.log("Collisions: {}".format(time.process_time() - st))

    for ship in me.get_ships():
        if planned_moves[ship.id] == CONSTRUCT:
            command_queue.append(ship.make_dropoff())
        else:
            command_queue.append(ship.move(planned_moves[ship.id]))

    consider_spawning()

    game.end_turn(command_queue)
