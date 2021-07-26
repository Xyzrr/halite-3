#!/usr/bin/env python3
# Python 3.6

import hlt

from hlt import constants

from hlt.positionals import Direction

import random

import logging

""" <<<Game Begin>>> """

game = hlt.Game()
# As soon as you call "ready" function below, the 2 second per turn timer will start.
game.ready("Naive")

logging.info("Successfully created bot! My Player ID is {}.".format(game.my_id))

ship_status = {}

""" <<<Game Loop>>> """

while True:
    game.update_frame()

    me = game.me
    game_map = game.game_map

    for pid, player in game.players.items():
        if pid != me.id:
            enemy = player

    command_queue = []

    for ship in me.get_ships():

        logging.info("Ship {} has {} halite.".format(ship.id, ship.halite_amount))
        if ship.id not in ship_status:
            ship_status[ship.id] = "exploring"

        if ship_status[ship.id] == "returning":
#            if me.halite_amount >= 4000:
#                command_queue.append(ship.make_dropoff())
#                continue
            if ship.position == me.shipyard.position:
                ship_status[ship.id] = "exploring"
            else:
                move = game_map.naive_navigate(ship, me.shipyard.position)
                command_queue.append(ship.move(move))
                continue
        elif ship.halite_amount >= constants.MAX_HALITE * .8:
            ship_status[ship.id] = "returning"

        if game_map[ship.position].halite_amount < constants.MAX_HALITE / 10 or ship.is_full:
            best_d = None
            most_hal = 0
            for d in Direction.get_all_cardinals():
                hal = game_map[ship.position.directional_offset(d)].halite_amount
                if hal > most_hal:
                    most_hal = hal
                    best_d = d
            command_queue.append(ship.move(best_d))
        else:
            command_queue.append(ship.stay_still())

    if game.turn_number <= 200 and me.halite_amount >= constants.SHIP_COST and not game_map[me.shipyard].is_occupied:
        command_queue.append(me.shipyard.spawn())

    game.end_turn(command_queue)
