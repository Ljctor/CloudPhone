"""Reads the text Slayer Legend writes in its pixel font, off a screenshot
(width, height, RGB bytes). Pure, stdlib only.

The game writes its titles, region and stage names, buttons and labels in
one pixel font, scaled: a capital is CAP font pixels high, a descender
goes 2 below (ROWS in all). A line of text is cut into glyphs (columns of
ink), each glyph's box runs from the line's top over ROWS font pixels, so
that a glyph's height and place in the line count (a "." is not an "I"),
and is matched, as ink coverage on each shape's grid, against the shapes
below: the closest wins, None (unread) when even it is too far.

The shapes are cut out of real 480x1040 captures (the fixtures whose text
fixtures/texts.json gives) by font_cut.py, each the average of at least
two occurrences; a character the game renders differently at two sizes
has a variant per rendering ("a~1"). A few capitals not seen twice yet
are drawn in the same style (DRAWN). A letter missing from FONT reads as
the closest shape or as None: compare words with close() where it may
be one.

Kept separate so that any screen reader may use it (stage names, the
Battle settings badge, soul weapon names, the engraving).
"""

CAP = 7
ROWS = 9
# How much a glyph's width (in font pixels) off its shape's counts.
WIDTH_WEIGHT = 0.02
# Beyond this distance a glyph is unread.
UNREAD = 0.12
# A run that reads as one glyph further than SPLIT_ABOVE is also tried
# as touching glyphs: the cut wins when its distances, plus SPLIT_COST per
# glyph, beat the one glyph's (two letters a fractional scale made touch
# read as one wide letter: "t'" as "t", "le" as "g").
SPLIT_ABOVE = 0.04
SPLIT_COST = 0.02

# The shapes, ROWS rows each (CAP for a capital, 2 more for descenders),
# as rows of "#" (ink) and "." or of digits 0-9 (an average coverage).
# BEGIN CUT FONT (font_cut.py --write)
# Cut from the fixtures by font_cut.py: each shape the average ink coverage
# (digits: tenths of ink, 9 full) of its occurrences; key: the character, or
# the character, ~ and a variant (another size's rendering).
FONT = {
    '%': ['671280', '642370', '772610', '233402', '007477', '027385', '032167', '010001', '000000'],
    '%~1': ['460280', '532480', '771510', '346523', '018485', '034277', '031014', '000000', '000000'],
    "'": ['9', '9', '9', '0', '0', '0', '0', '0', '0'],
    '+': ['0110', '0330', '5665', '5885', '0440', '0110', '0000', '0000', '0000'],
    '.': ['0', '0', '0', '0', '0', '0', '9', '2', '0'],
    '0': ['4994', '5116', '5006', '5006', '5006', '6127', '4885', '0110', '0000'],
    '2': ['4994', '5115', '1037', '0473', '4710', '9422', '8888', '0000', '0000'],
    '3': ['6996', '5226', '0257', '0266', '0006', '3005', '7997', '1221', '0000'],
    '4': ['00160', '01880', '17250', '85161', '97798', '33363', '00040', '00000', '00000'],
    '7': ['9999', '2226', '0047', '0064', '0273', '0330', '0330', '0110', '0000'],
    ':': ['1', '7', '0', '0', '4', '4', '0', '0', '0'],
    'A': ['14940', '28981', '68686', '96159', '98789', '97369', '95059', '11011', '00000'],
    'A~1': ['05840', '17481', '86388', '82279', '97789', '93279', '71057', '00000', '00000'],
    'A~2': ['03930', '06260', '57075', '92029', '98789', '95459', '92029', '20002', '00000'],
    'A~3': ['0330', '0453', '0564', '7215', '9547', '9778', '9105', '1000', '0000'],
    'C': ['38777', '82000', '80000', '80000', '80000', '80000', '17777', '00000', '00000'],
    'E': ['97777', '93000', '95441', '95431', '93000', '93000', '87666', '00000', '00000'],
    'G': ['39999', '84333', '91133', '91489', '91008', '91018', '69999', '00000', '00000'],
    'I': ['99', '77', '55', '55', '55', '55', '99', '00', '00'],
    'K': ['92059', '92252', '97910', '98000', '98710', '93640', '92069', '20002', '00000'],
    'M': ['70007', '96069', '53835', '40604', '40004', '40004', '40004', '00000', '00000'],
    'O': ['268893', '862126', '961007', '961007', '961007', '961007', '566666', '011110', '000000'],
    'O~1': ['298892', '940069', '940069', '940069', '940069', '940069', '386684', '022220', '000000'],
    'R': ['9995', '9549', '9219', '9777', '9993', '9593', '9249', '1001', '0000'],
    'S': ['5888', '7211', '8662', '2667', '0017', '4016', '5885', '0110', '0000'],
    'S~1': ['49999', '94222', '78760', '15588', '21069', '95479', '48883', '01100', '00000'],
    'S~2': ['3999', '9444', '8442', '2667', '1009', '9119', '4995', '0110', '0000'],
    'T': ['99999', '13931', '02920', '02920', '02920', '02920', '02920', '00200', '00000'],
    'U': ['94049', '94049', '94049', '94049', '94049', '96269', '28682', '01110', '00000'],
    'V': ['92059', '92059', '92059', '86278', '29580', '15840', '02710', '00000', '00000'],
    'W': ['92065029', '92065029', '77487477', '18677581', '18777681', '04823840', '02701720', '00100100', '00000000'],
    'W~1': ['92038006', '92038006', '95069358', '06061583', '06061583', '03530471', '01910410', '00200100', '00000000'],
    'X': ['7039', '8039', '5871', '0620', '2640', '8459', '8039', '0000', '0000'],
    'X~1': ['9119', '9229', '6886', '0830', '3873', '7337', '9119', '2002', '0000'],
    'X~2': ['92029', '93149', '47784', '01910', '16861', '75257', '92029', '20002', '00000'],
    'a': ['00000', '01110', '38984', '15579', '66579', '91049', '68999', '01111', '00000'],
    'a~1': ['00000', '14441', '17896', '16689', '77669', '95139', '38888', '00000', '00000'],
    'a~2': ['00000', '05550', '06678', '28899', '84359', '85469', '07888', '00000', '00000'],
    'a~3': ['0000', '0110', '0466', '0679', '4447', '9105', '4557', '0111', '0000'],
    'c': ['0000', '0222', '6999', '9400', '9400', '9400', '5999', '0111', '0000'],
    'c~1': ['0000', '0011', '4555', '9300', '9300', '9300', '4555', '0011', '0000'],
    'd': ['00049', '03359', '67679', '91179', '91049', '73259', '16888', '00000', '00000'],
    'd~1': ['00007', '01107', '16717', '85258', '94007', '94007', '57558', '01111', '00000'],
    'd~2': ['0019', '0119', '4949', '5259', '5019', '5019', '4569', '0111', '0000'],
    'e': ['0000', '1331', '6776', '9779', '8444', '7211', '3777', '0000', '0000'],
    'e~1': ['0000', '1220', '6996', '9669', '9777', '8100', '6999', '0111', '0000'],
    'e~2': ['0000', '1551', '6877', '9889', '9655', '9654', '2888', '0000', '0000'],
    'f': ['176', '430', '654', '572', '420', '420', '420', '000', '000'],
    'g': ['0000', '1333', '6889', '9119', '9119', '6999', '1569', '2773', '0000'],
    'g~1': ['0000', '0111', '5569', '7117', '7117', '4889', '1448', '1552', '0000'],
    'g~2': ['00000', '15555', '58899', '95169', '95279', '49999', '18998', '15550', '00000'],
    'h': ['93000', '95651', '97897', '97259', '93059', '93059', '73048', '00000', '00000'],
    'i': ['39', '45', '89', '49', '39', '39', '38', '00', '00'],
    'i~1': ['09', '24', '99', '19', '09', '09', '08', '01', '00'],
    'i~2': ['05', '12', '89', '16', '06', '06', '06', '01', '00'],
    'i~3': ['09', '89', '69', '09', '09', '09', '08', '00', '00'],
    'l': ['9', '9', '9', '9', '9', '9', '9', '1', '0'],
    'm': ['000000', '443341', '988888', '816618', '816618', '816618', '715517', '000000', '000000'],
    'n': ['0000', '4441', '9777', '9119', '9119', '9119', '8018', '0000', '0000'],
    'n~1': ['0000', '1110', '9995', '8029', '8029', '8029', '8029', '1001', '0000'],
    'n~2': ['0000', '1110', '9874', '7116', '7107', '7107', '7107', '1001', '0000'],
    'n~3': ['00000', '56660', '98786', '96169', '96069', '96069', '85058', '00000', '00000'],
    'o': ['00000', '04440', '67776', '93049', '93039', '84358', '17871', '00000', '00000'],
    'o~1': ['0000', '0110', '5995', '6116', '6006', '6006', '6776', '1111', '0000'],
    'o~2': ['0000', '0220', '4996', '9209', '9209', '9209', '5996', '0220', '0000'],
    'p': ['00000', '77761', '98778', '96029', '96239', '99883', '96110', '65000', '10000'],
    'p~1': ['0000', '3331', '9887', '9119', '9339', '9995', '9431', '7100', '0000'],
    'p~2': ['0000', '2221', '9997', '5005', '5005', '7554', '7552', '4000', '0000'],
    'p~3': ['0000', '1110', '9980', '6237', '5019', '6237', '9530', '5000', '2000'],
    'q': ['0000', '1444', '7999', '7028', '7249', '4889', '0028', '0026', '0001'],
    'r': ['000', '333', '988', '930', '930', '930', '830', '100', '000'],
    'r~1': ['000', '444', '977', '700', '700', '700', '600', '000', '000'],
    'r~2': ['000', '111', '975', '710', '700', '700', '700', '000', '000'],
    's': ['0000', '0111', '5999', '8661', '2566', '7029', '7995', '0110', '0000'],
    's~1': ['0000', '1333', '6888', '7662', '2569', '9449', '3883', '0000', '0000'],
    's~2': ['0000', '0444', '6666', '6772', '2238', '7337', '0880', '0000', '0000'],
    't': ['0820', '4854', '7987', '1820', '0820', '1853', '0288', '0000', '0000'],
    't~1': ['1600', '2622', '8988', '2611', '1600', '1600', '0466', '0011', '0000'],
    't~2': ['3920', '3931', '9999', '3920', '3920', '3920', '1699', '0011', '0000'],
    'u': ['0000', '4015', '7019', '7019', '7019', '8249', '3888', '0000', '0000'],
    'u~1': ['0000', '1001', '5005', '5005', '5005', '5005', '7999', '1222', '0000'],
    'v': ['0000', '4014', '8129', '7467', '3683', '1671', '0550', '0000', '0000'],
    'v~1': ['0000', '0001', '5019', '4154', '4150', '1730', '0830', '0100', '0000'],
    'w': ['0000000', '4406416', '9707519', '9757729', '9887849', '3882475', '0870272', '0100010', '0000000'],
    'w~1': ['000000', '302213', '817729', '837859', '855779', '572495', '371283', '000010', '000000'],
}
# Where each shape was cut: (occurrences, fixtures).
SOURCES = {
    '%': (2, ['eg_popup_locked', 'eg_popup_unlocked']),
    '%~1': (2, ['eg_popup_locked', 'eg_popup_unlocked']),
    "'": (9, ['banner_giants_glass', 'battle_name_920', 'battle_name_920_b', 'row_913', 'row_914', 'row_915', 'row_918', 'row_919', 'row_920']),
    '+': (2, ['eg_popup_locked', 'eg_popup_unlocked']),
    '.': (2, ['eg_popup_locked', 'eg_popup_unlocked']),
    '0': (7, ['eg_popup_locked', 'eg_popup_unlocked', 'sw_owned_0']),
    '2': (2, ['eg_popup_locked', 'eg_popup_unlocked']),
    '3': (2, ['eg_popup_locked', 'eg_popup_unlocked']),
    '4': (2, ['eg_popup_locked', 'eg_popup_unlocked']),
    '7': (2, ['eg_popup_locked', 'eg_popup_unlocked']),
    ':': (2, ['sw_owned_0', 'sw_owned_1']),
    'A': (4, ['controls_iii_auto_on', 'controls_iv', 'sign_in_buttons', 'sw_tabs']),
    'A~1': (2, ['battle_menu_labels', 'sw_name_ambition']),
    'A~2': (2, ['eg_popup_locked', 'eg_popup_unlocked']),
    'A~3': (2, ['eg_popup_locked', 'eg_popup_unlocked']),
    'C': (2, ['battle_menu_labels']),
    'E': (10, ['battle_menu_labels', 'eg_cards', 'eg_popup_locked', 'eg_popup_unlocked', 'eg_title']),
    'G': (22, ['banner_giants_glass', 'battle_name_920', 'battle_name_920_b', 'eg_popup_locked', 'eg_popup_unlocked', 'row_913', 'row_914', 'row_915', 'row_918', 'row_919', 'row_920', 'sign_in_buttons', 'sw_name_grand']),
    'I': (8, ['row_913', 'row_914', 'row_918', 'row_919']),
    'K': (2, ['eg_popup_locked', 'eg_popup_unlocked']),
    'M': (2, ['eg_popup_locked', 'eg_popup_unlocked']),
    'O': (4, ['battle_menu_labels', 'eg_popup_locked', 'eg_popup_unlocked', 'sw_owned_0']),
    'O~1': (3, ['controls_iii_auto_on', 'controls_iv', 'sw_owned_1']),
    'R': (2, ['sw_tabs', 'title_select_region']),
    'S': (4, ['battle_menu_labels', 'eg_popup_locked', 'eg_popup_unlocked']),
    'S~1': (3, ['sign_in_buttons', 'sw_tabs', 'sw_title']),
    'S~2': (3, ['eg_title', 'sign_in_buttons', 'title_select_region']),
    'T': (4, ['controls_iii_auto_on', 'controls_iv', 'eg_popup_locked', 'eg_popup_unlocked']),
    'U': (3, ['controls_iii_auto_on', 'controls_iv', 'sw_tag_unequip']),
    'V': (5, ['eg_title', 'row_914', 'row_915', 'row_918', 'sw_name_vision']),
    'W': (3, ['eg_title', 'sw_tabs', 'sw_title']),
    'W~1': (2, ['eg_popup_locked', 'eg_popup_unlocked']),
    'X': (8, ['row_913', 'row_914', 'row_915', 'row_918', 'row_919', 'row_920']),
    'X~1': (2, ['battle_name_920', 'battle_name_920_b']),
    'X~2': (2, ['battle_name_920', 'battle_name_920_b']),
    'a': (22, ['banner_giants_glass', 'battle_name_920', 'battle_name_920_b', 'eg_popup_locked', 'eg_popup_unlocked', 'row_913', 'row_914', 'row_915', 'row_918', 'row_919', 'row_920']),
    'a~1': (6, ['battle_menu_labels', 'eg_title', 'settings_title', 'sw_tabs']),
    'a~2': (3, ['battle_menu_labels', 'sw_name_grand', 'sw_title']),
    'a~3': (2, ['eg_popup_locked', 'eg_popup_unlocked']),
    'c': (5, ['battle_menu_labels', 'sw_tabs', 'title_select_region']),
    'c~1': (2, ['eg_popup_locked', 'eg_popup_unlocked']),
    'd': (5, ['battle_menu_labels', 'eg_popup_locked', 'eg_popup_unlocked', 'sw_name_grand', 'sw_owned_1']),
    'd~1': (3, ['eg_popup_locked', 'eg_popup_unlocked', 'sw_owned_0']),
    'd~2': (2, ['eg_popup_locked', 'eg_popup_unlocked']),
    'e': (11, ['battle_menu_labels', 'eg_popup_locked', 'eg_popup_unlocked', 'settings_title', 'sw_owned_0', 'sw_owned_1']),
    'e~1': (10, ['eg_popup_locked', 'eg_popup_unlocked', 'eg_title', 'sw_tabs', 'title_select_region']),
    'e~2': (5, ['settings_title', 'sign_in_buttons', 'sw_tag_unequip', 'sw_title']),
    'f': (4, ['eg_popup_locked', 'eg_popup_unlocked']),
    'g': (4, ['eg_title', 'settings_title', 'title_select_region']),
    'g~1': (4, ['eg_popup_locked', 'eg_popup_unlocked']),
    'g~2': (3, ['sign_in_buttons']),
    'h': (3, ['battle_menu_labels', 'sign_in_buttons']),
    'i': (19, ['battle_menu_labels', 'eg_title', 'row_913', 'row_914', 'row_915', 'row_918', 'row_919', 'row_920', 'settings_title', 'sign_in_buttons', 'sw_name_ambition', 'sw_name_vision', 'sw_tabs', 'title_select_region']),
    'i~1': (12, ['banner_giants_glass', 'battle_menu_labels', 'eg_popup_locked', 'eg_popup_unlocked', 'eg_title', 'sw_name_ambition', 'sw_tabs', 'sw_tag_unequip']),
    'i~2': (7, ['battle_name_920', 'battle_name_920_b', 'eg_popup_locked', 'eg_popup_unlocked', 'sw_tabs']),
    'i~3': (2, ['sign_in_buttons']),
    'l': (24, ['banner_giants_glass', 'battle_menu_labels', 'battle_name_920', 'battle_name_920_b', 'eg_popup_locked', 'eg_popup_unlocked', 'eg_title', 'row_913', 'row_914', 'row_915', 'row_918', 'row_919', 'row_920', 'settings_title', 'sign_in_buttons', 'sw_tabs', 'sw_title', 'title_select_region']),
    'm': (3, ['battle_menu_labels', 'sw_name_ambition']),
    'n': (15, ['battle_menu_labels', 'eg_popup_locked', 'eg_popup_unlocked', 'eg_title', 'settings_title', 'sw_name_ambition', 'sw_name_grand', 'sw_name_vision', 'sw_tag_unequip', 'sw_title']),
    'n~1': (12, ['banner_giants_glass', 'battle_name_920', 'battle_name_920_b', 'row_913', 'row_914', 'row_915', 'row_918', 'row_919', 'row_920', 'sw_owned_1', 'sw_tabs', 'title_select_region']),
    'n~2': (12, ['eg_popup_locked', 'eg_popup_unlocked', 'eg_title', 'sw_owned_0']),
    'n~3': (4, ['sign_in_buttons']),
    'o': (15, ['battle_menu_labels', 'eg_popup_locked', 'eg_popup_unlocked', 'eg_title', 'sign_in_buttons', 'sw_name_ambition', 'sw_name_vision', 'sw_title']),
    'o~1': (8, ['eg_popup_locked', 'eg_popup_unlocked']),
    'o~2': (3, ['sw_tabs', 'title_select_region']),
    'p': (5, ['battle_menu_labels', 'sign_in_buttons', 'sw_title']),
    'p~1': (4, ['eg_title', 'sw_tabs', 'sw_tag_unequip']),
    'p~2': (2, ['eg_popup_locked', 'eg_popup_unlocked']),
    'p~3': (2, ['eg_popup_locked', 'eg_popup_unlocked']),
    'q': (2, ['battle_menu_labels', 'sw_tag_unequip']),
    'r': (5, ['battle_menu_labels', 'eg_title', 'sw_name_grand', 'sw_tabs']),
    'r~1': (4, ['battle_menu_labels', 'eg_popup_locked', 'eg_popup_unlocked']),
    'r~2': (2, ['eg_popup_locked', 'eg_popup_unlocked']),
    's': (32, ['banner_giants_glass', 'battle_name_920', 'battle_name_920_b', 'eg_popup_locked', 'eg_popup_unlocked', 'row_913', 'row_914', 'row_915', 'row_918', 'row_919', 'row_920', 'sw_tabs']),
    's~1': (3, ['eg_title', 'settings_title']),
    's~2': (3, ['eg_popup_locked', 'eg_popup_unlocked', 'sw_name_vision']),
    't': (10, ['battle_menu_labels', 'eg_popup_locked', 'eg_popup_unlocked', 'settings_title', 'sign_in_buttons', 'sw_name_ambition']),
    't~1': (10, ['battle_menu_labels', 'battle_name_920', 'battle_name_920_b', 'eg_popup_locked', 'eg_popup_unlocked']),
    't~2': (9, ['banner_giants_glass', 'row_913', 'row_914', 'row_915', 'row_918', 'row_919', 'row_920', 'sw_tabs', 'title_select_region']),
    'u': (5, ['battle_menu_labels', 'eg_title', 'sw_tag_unequip', 'sw_title']),
    'u~1': (2, ['eg_popup_locked', 'eg_popup_unlocked']),
    'v': (2, ['battle_menu_labels', 'eg_title']),
    'v~1': (2, ['eg_popup_locked', 'eg_popup_unlocked']),
    'w': (2, ['sign_in_buttons', 'sw_owned_0']),
    'w~1': (2, ['sign_in_buttons', 'sw_owned_1']),
}
# END CUT FONT

# Cut from one capture before the fixtures kept their text (not averaged
# yet): re-cut by font_cut.py once two occurrences are in fixtures/.
CUT_ONCE = {}
# Drawn in the same style, for capitals no fixture shows twice yet: each
# goes as soon as font_cut.py cuts it (docs/TODO.md lists them).
DRAWN = {
    "B": ["####.", "#...#", "#...#", "####.", "#...#", "#...#", "####.", ".....", "....."],
    "D": ["####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####.", ".....", "....."],
}
for _extra in (CUT_ONCE, DRAWN):
    FONT.update({char: shape for char, shape in _extra.items() if not any(key[0] == char for key in FONT)})


def crop(shot, area, channel=max):
    """Grey levels of an area ((left, top, right, bottom) fractions) of the
    screenshot, as rows of ints; channel(r, g, b) makes the grey (max: a
    white text and a coloured one alike)."""
    width, height, pixels = shot
    left, top = max(0, int(area[0] * width)), max(0, int(area[1] * height))
    right, bottom = min(width, int(area[2] * width)), min(height, int(area[3] * height))
    rows = []
    for y in range(top, bottom):
        base = y * width * 3
        rows.append([channel(pixels[base + 3 * x], pixels[base + 3 * x + 1], pixels[base + 3 * x + 2])
                     for x in range(left, right)])
    return rows


def ink(rows, level=None, share=0.6, contrast=40):
    """Binary ink: brighter than level, or than share of the way from the
    area's darkest to its brightest pixel. None when the area has no
    contrast (no text)."""
    flat = [v for row in rows for v in row]
    if not flat:
        return None
    low, high = min(flat), max(flat)
    if high - low < contrast:
        return None
    if level is None:
        level = low + (high - low) * share
    return [[v > level for v in row] for row in rows]


def lines(ink, least=4):
    """The text lines of an ink area, as (top, bottom) rows: runs of rows
    with ink, at least least rows high."""
    found, top = [], None
    for y, row in enumerate(ink + [[]]):
        if any(row):
            top = y if top is None else top
        elif top is not None:
            if y - top >= least:
                found.append((top, y - 1))
            top = None
    return found


def _runs(ink, top, bottom):
    """Columns of ink between rows top and bottom, as (left, right)."""
    width = len(ink[0])
    used = [any(ink[y][x] for y in range(top, bottom + 1)) for x in range(width)]
    runs, x = [], 0
    while x < width:
        if used[x]:
            right = x
            while right + 1 < width and used[right + 1]:
                right += 1
            runs.append((x, right))
            x = right + 1
        else:
            x += 1
    return runs


def _bottom(ink, top, bottom, run):
    left, right = run
    return max(y for y in range(top, bottom + 1) if any(ink[y][left:right + 1]))


def metrics(ink, top, bottom):
    """(glyph columns, cap height in pixels) of a line: the cap height runs
    from the line's top to the bottom most glyphs stand on (glyphs at
    least half the line's height: not an apostrophe; the higher on a tie:
    not a descender)."""
    runs = _runs(ink, top, bottom)
    if not runs:
        return [], 0
    bottoms = [_bottom(ink, top, bottom, run) for run in runs]
    tall = [b for b in bottoms if b - top + 1 >= (bottom - top + 1) / 2] or bottoms
    base = max(set(tall), key=lambda b: (tall.count(b), -b))
    return runs, base - top + 1


def _grid(ink, box, cols, rows):
    """Ink coverage of a box (left, right, top, bottom; rows past the ink
    are empty) on a cols x rows grid."""
    left, right, top, bottom = box
    height = len(ink)
    w, h = right - left + 1, bottom - top + 1
    grid = []
    for gy in range(rows):
        y0, y1 = top + gy * h / rows, top + (gy + 1) * h / rows
        row = []
        for gx in range(cols):
            x0, x1 = left + gx * w / cols, left + (gx + 1) * w / cols
            total = covered = 0.0
            for y in range(int(y0), min(bottom + 1, int(y1 + 0.999))):
                fy = min(y + 1, y1) - max(y, y0)
                for x in range(int(x0), min(right + 1, int(x1 + 0.999))):
                    fx = min(x + 1, x1) - max(x, x0)
                    total += fx * fy
                    if y < height and ink[y][x]:
                        covered += fx * fy
            row.append(covered / total if total else 0.0)
        grid.append(row)
    return grid


_LEVELS = {"#": 1.0, ".": 0.0, **{str(n): n / 9 for n in range(10)}}
_VALUES = {}


def _values(shape):
    """A shape's ink coverage per cell: "#" 1, "." 0, a digit n n/9 (an
    average of the captures' coverage)."""
    key = tuple(shape)
    if key not in _VALUES:
        _VALUES[key] = [[_LEVELS[c] for c in row] for row in shape]
    return _VALUES[key]


def ink_of(cell):
    """Whether a shape's cell is ink ("#", or a coverage of at least half)."""
    return _LEVELS[cell] >= 0.5


def match(ink, box, cap, font=None, only=None):
    """(the closest character, its distance) for a glyph box (left, right,
    top, bottom) on a line of cap height cap; only: the characters allowed.
    A font's key is its character, alone or followed by "~" and the size
    class of a variant (VARIANT)."""
    font = font or FONT
    left, right, top, bottom = box
    width = (right - left + 1) * CAP / cap
    best, distance = None, None
    grids = {}
    for key, shape in font.items():
        if only is not None and key[0] not in only:
            continue
        cols = len(shape[0])
        if cols not in grids:
            grids[cols] = _grid(ink, box, cols, ROWS)
        grid = grids[cols]
        values = _values(shape)
        d = sum((grid[y][x] - values[y][x]) ** 2 for y in range(ROWS) for x in range(cols)) / (cols * ROWS)
        d += WIDTH_WEIGHT * (width - cols) ** 2
        if distance is None or d < distance:
            best, distance = key[0], d
    return best, distance


def _split(ink, run, top, box_bottom, cap, font, only):
    """The glyphs of one column run, as [(character, distance, (left,
    right))]: one glyph, or, when it reads badly or is too wide for one
    (letters a fractional scale made touch), the cut into glyphs that reads
    best."""
    left, right = run
    chars = [key for key in font if only is None or key[0] in only]
    widest = max(len(font[key][0]) for key in chars)
    width = (right - left + 1) * CAP / cap
    if width > 4 * (widest + 1):
        return [(None, 1.0, run)]  # a bar or a border, not text
    char, d = match(ink, (left, right, top, box_bottom), cap, font, only)
    single = d <= UNREAD and width <= widest + 1
    if single and d <= SPLIT_ABOVE:
        return [(char, d, run)]
    # Each character only at about its own width.
    widths = {}
    for c in chars:
        size = len(font[c][0]) * cap / CAP
        for w in range(max(1, int(size) - 1), int(size) + 4):
            widths.setdefault(w, []).append(c)
    best = {left: (0.0, [])}
    for end in range(left, right + 1):
        options = []
        for w, candidates in widths.items():
            start = end - w + 1
            if start not in best:
                continue
            c, dist = match(ink, (start, end, top, box_bottom), cap, {key: font[key] for key in candidates})
            options.append((best[start][0] + dist + SPLIT_COST, best[start][1] + [(c, dist, (start, end))]))
        if options:
            best[end + 1] = min(options, key=lambda option: option[0])
    if right + 1 not in best or single and best[right + 1][0] >= d + SPLIT_COST:
        return [(char, d, run)] if single else [(None, 1.0, run)]
    return best[right + 1][1]


def read_line(ink, top, bottom, font=None, only=None, space=0.3):
    """The words of a line, as lists of (character or None, distance,
    (left, right)); a gap wider than space times the cap height parts two
    words."""
    font = font or FONT
    runs, cap = metrics(ink, top, bottom)
    if not runs or cap < 4:
        return []
    box_bottom = top + round(cap * ROWS / CAP) - 1
    words, word, last = [], [], None
    for run in runs:
        if word and run[0] - last - 1 > space * cap:
            words.append(word)
            word = []
        for char, distance, cut in _split(ink, run, top, box_bottom, cap, font, only):
            word.append((char if distance <= UNREAD else None, distance, cut))
        last = run[1]
    if word:
        words.append(word)
    return words


def text(words):
    """A line's words as a string, "?" for an unread glyph."""
    return " ".join("".join(char or "?" for char, _, _ in word) for word in words)


def read(shot, area, level=None, font=None, only=None, channel=max, caps=None, most=40):
    """[(text, top, bottom)] of every line in area; top and bottom are
    fractions of the screen. channel and level: see crop and ink (min with
    a high level keeps a white text only, off a bright background). caps:
    (lowest, highest) cap height as fractions of the screen height, the
    other lines are skipped; so is a line of more than most glyph columns
    (not text: reading it would only cost time)."""
    rows = crop(shot, area, channel)
    marks = ink(rows, level)
    if not marks:
        return []
    height = shot[1]
    first = int(area[1] * height)
    found = []
    for top, bottom in lines(marks):
        runs, cap = metrics(marks, top, bottom)
        if len(runs) > most or caps and not caps[0] <= cap / height <= caps[1]:
            continue
        found.append((text(read_line(marks, top, bottom, font, only)), (first + top) / height,
                      (first + bottom + 1) / height))
    return found


def distance(a, b):
    """Edit distance between two strings ("?" matches anything)."""
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            same = ca == cb or "?" in (ca, cb)
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (0 if same else 1)))
        previous = current
    return previous[-1]


def close(read_text, names, most=0.25, margin=1):
    """The name read_text reads as: the closest of a closed list of names,
    when it is within most edits per character and every other is at
    least margin edits further. None otherwise (unknown)."""
    if not read_text:
        return None
    key = read_text.replace(" ", "").lower()
    scored = sorted((distance(key, name.replace(" ", "").lower()), name) for name in names)
    if not scored or scored[0][0] > most * max(len(key), 1):
        return None
    if len(scored) > 1 and scored[1][0] - scored[0][0] < max(1, margin):
        return None
    return scored[0][1]


ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50}


def roman(letters):
    """The value of a Roman numeral ("XIV": 14), None if it is not one."""
    if not letters or any(c not in ROMAN for c in letters):
        return None
    total, previous = 0, 0
    for c in reversed(letters):
        value = ROMAN[c]
        total = total - value if value < previous else total + value
        previous = max(previous, value)
    return total


def shape_of(char, font=None):
    """char's shape in font: its own key, else its first variant's."""
    font = font or FONT
    if char in font:
        return font[char]
    return next(shape for key, shape in font.items() if key[0] == char)


def render(string, scale=2, font=None, gap=1, space=3):
    """A synthetic line of text: rows of 0/1, string drawn from font at
    scale (tests and calibration checks). A cell of coverage v (a cut
    shape's digit) gets round(v x scale x scale) of its scale x scale
    pixels, so that reading it back samples about v again."""
    font = font or FONT
    columns = []
    for i, char in enumerate(string):
        if char == " ":
            columns.extend([[0.0] * ROWS] * space)
            continue
        shape = shape_of(char, font)
        for x in range(len(shape[0])):
            columns.append([_LEVELS[shape[y][x]] for y in range(ROWS)])
        if i + 1 < len(string) and string[i + 1] != " ":
            columns.extend([[0.0] * ROWS] * gap)
    rows = [[0] * (len(columns) * scale) for _ in range(ROWS * scale)]
    for x, column in enumerate(columns):
        for y, value in enumerate(column):
            # Spread over the cell's rows first (no row of a glyph left empty).
            for n in range(round(value * scale * scale)):
                rows[y * scale + n % scale][x * scale + (n // scale + n % scale) % scale] = 1
    return rows


def numeral(ink):
    """The Roman numeral I to V alone in an ink area, by its strokes, in
    any font (the serif buttons and badge of Battle settings too): the
    strokes cut by a row a third down and by one three quarters down (a V
    has two at the top, one at the bottom; an I one in both). None
    otherwise."""
    if not ink:
        return None
    ys = [y for y, row in enumerate(ink) if any(row)]
    if len(ys) < 5:
        return None
    top, height = ys[0], ys[-1] - ys[0] + 1

    def strokes(fraction):
        row = ink[top + int(height * fraction)]
        return sum(1 for x, v in enumerate(row) if v and (x == 0 or not row[x - 1]))

    return {(1, 1): 1, (2, 2): 2, (3, 3): 3, (3, 2): 4, (2, 1): 5}.get((strokes(1 / 3), strokes(3 / 4)))
