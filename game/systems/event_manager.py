class EventManager:
    def __init__(self):
        self.listeners = {}

    def subscribe(
        self,
        event_name: str,
        callback,
    ):
        self.listeners.setdefault(
            event_name,
            [],
        ).append(callback)

    def emit(
        self,
        event_name: str,
        *args,
        **kwargs,
    ):
        for callback in self.listeners.get(
            event_name,
            [],
        ):
            callback(
                *args,
                **kwargs,
            )
