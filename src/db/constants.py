from enum import IntEnum


class DatabaseEntryState(IntEnum):
    # 0 ~ 499 are predefined states.
    OK = 0
    PROCESSING = 1
    PROCESSED = 2
    TIMED_OUT = 10
    CANCELLED = 11

    # 500 ~ 999 are custom states
    CUSTOM = 500

    # 1000+ are error states.
    ERROR = 1000

    # 9999 is the maximum, indicating deleted
    DELETED = 9999


class TriageEntryState(IntEnum):
    # A debugger has connected to the provided connection
    CONNECTED = DatabaseEntryState.CUSTOM

    # Trying to connect
    CONNECTING = DatabaseEntryState.CUSTOM + 1

    # Disconnected
    DISCONNECTED = DatabaseEntryState.CUSTOM + 2


class DumpTriageState(IntEnum):
    NONE = 0

    TRIAGED = 1
