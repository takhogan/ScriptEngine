class ScriptRun:
    def __init__(self, state, context, state_updates, actions):
        self.state = state
        self.context = context
        self.state_updates = state_updates
        self.actions = actions