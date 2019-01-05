DICT_STATES_DATA_TABLE = {
    0: 'new',
    1: 'current',
    2: 'won',
    3: 'lost',
    4: 'waiting',
    5: 'paused',
    6: 'current_paused',
    7: 'new_paused',
}

STATES_DATA_TABLE = (
    (0, 'new'),
    (1, 'current'),
    (2, 'won'),
    (3, 'lost'),
    (4, 'waiting'),
    (5, 'paused'),
    (6, 'current_paused'),
    (7, 'new_paused'),
)

TEAM_DIFFERENCE = 4
MIN_PER_TEAM = 1.5
MIN_PARITY = 3
LAPSE_MATCH_IN_MIN = 130

INIT_AMOUNT = 2
LIMIT_ROWS = 70

# (S) VALUES TO FACTOR PARITY FORMULA
FIRST_VAL_FORMULA = 46
SECOND_VAL_FORMULA = 0.78
THRID_VALUE_FORMULA = 1
MIN_VAL_INIT = 3.20
STEP_PARITY_FORMULA = 0.04
# (E) VALUES TO FACTOR PARITY FORMULA

BETTING_HOME = "inkabet"
MATCH_SUSPENDED_HOURS = 24
MAX_TIME_ATTEMPS_MINUTES = 5
