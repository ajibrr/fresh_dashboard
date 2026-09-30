def enabled_conditions(conditions):
    """
    Every condition in the config must explicitly say "enabled": true or
    false — no default. Setting it to false lets a condition stay in
    analyze.json (visible, still fully parameterized) without being
    executed, instead of having to delete/comment it out to turn it off.
    """
    return [c for c in conditions if c["enabled"]]


class StrategyDefinition:
    """Thin wrapper around a strategy config dict — same role as this
    project's option-premium sibling's StrategyDefinition, adapted for a
    two-directional (LONG/SHORT) candle-breakout strategy."""

    def __init__(self, config):
        self.config = config
        self.name = config.get("name", "unnamed_strategy")
        self.entry = config.get("entry", {})

    def entry_conditions(self, direction):
        return enabled_conditions(self.entry.get(direction, {}).get("conditions", []))
