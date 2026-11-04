"""Inspect commands independently of context-menu grouping."""


def walk_actions(menu):
    for action in menu.actions():
        yield action
        child = action.menu()
        if child is not None:
            yield from walk_actions(child)


def find_action(menu, text):
    return next(action for action in walk_actions(menu) if action.text().split('\t', 1)[0] == text)
