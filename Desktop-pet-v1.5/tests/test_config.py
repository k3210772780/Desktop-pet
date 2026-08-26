from desktop_pet.config import DEFAULTS, load_config


def test_defaults_have_expected_keys():
    assert set(DEFAULTS) == {"follow_cursor_position", "walk_speed", "do_not_disturb",
                             "screen_intro_shown"}
    assert set(load_config()) == set(DEFAULTS)
