#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import random
import sys
import time

def get_line(count: int, content: str=None, chance: int=100):
    """Lines to yield"""
    counter = 0

    if count == 0:
        return None

    while True:
        # How frequently do we use the manually provided content
        rand_value = random.randint(0, 100)
        if content and rand_value <= chance:
            line = content
        else:
            line = f'Line output: {counter}'

        if counter >= count:
            return line

        else:
            yield line

            if count > -1:
                counter += 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-l', '--lines', default=10, type=int,
                        help='Number of lines to write, -1 writes until stopped')
    parser.add_argument('-m', '--manual', default=None, type=str,
                        help='Provide content for the line')
    parser.add_argument('-p', '--probability', default=100, type=float,
                        help='How often to print the manual line vs standard, 0-100')
    parser.add_argument('-e', '--stderr', default=False, type=bool,
                        help='Print lines to standard error, default False')
    parser.add_argument('-s', '--sleep', default=None, type=float,
                        help='Seconds (float) to sleep between lines, default 0; '
                             'default 1 when lines is -1')

    args = parser.parse_args()

    # Sleep duration
    if args.lines == -1:
        sleep_seconds = args.sleep if args.sleep else 1
    else:
        sleep_seconds = args.sleep if args.sleep else 0

    # Output
    if args.stderr:
        pipe = sys.stderr
    else:
        pipe = sys.stdout


    manual_chance = random.randint(0, 100)

    for line in get_line(count=args.lines, content=args.manual, chance=args.probability):
        pipe.write(f'{line}\n')
        time.sleep(sleep_seconds)
