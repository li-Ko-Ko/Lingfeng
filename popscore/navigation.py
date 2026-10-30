"""Report manual scrollbar movement after Qt has applied the new value."""
from PySide6.QtCore import QTimer


def watch_scrollbar(bar, notify):
    pending={'action':False}
    def arm(action):
        pending['action']=True
        # A clamped action may never emit valueChanged. Do not let it mark a
        # later programmatic follow/layout change as user navigation.
        QTimer.singleShot(0,bar,lambda:pending.update(action=False))
    def changed(value):
        manual=bar.isSliderDown() or pending['action']
        pending['action']=False
        if manual:notify()
    bar.actionTriggered.connect(arm)
    bar.valueChanged.connect(changed)
