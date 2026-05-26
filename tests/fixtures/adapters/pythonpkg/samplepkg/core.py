def operation() -> bool:
    return True


def actor() -> str:
    return "fixture-actor"


def state_change() -> str:
    return "changed"


class Service:
    def execute(self) -> bool:
        return operation()

