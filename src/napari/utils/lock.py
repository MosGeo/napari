import inspect
from collections.abc import Sequence
from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, model_validator


class LockMode(StrEnum):
    """Lock modes for the Lock class. These modes define how the lock value is interpreted."""

    EXACT = 'exact'
    IN_LIST = 'in_list'
    IN_RANGE = 'in_range'
    LARGER_THAN = 'larger_than'
    SMALLER_THAN = 'smaller_than'


class Lock(BaseModel, validate_assignment=True):
    """A lock class to be used as a locking mechanism for a certain attribute.

    Attributes:
        value (Any): The value of the lock.
        is_locked (bool | None): Whether the lock is active or not.
        is_hard_lock (bool | None): Whether the lock is a hard lock or a soft lock.
        mode (LockMode | None): The mode of the lock.
        comments (str | None): Comments about the lock.
    """

    value: Any
    is_locked: bool | None = True
    is_hard_lock: bool | None = True
    mode: LockMode | None = LockMode.EXACT
    comments: str | None = ''
    owner: str | None = None

    def __str__(self):
        return f'Lock value: {self.value}, lock mode: {self.mode}, locked: {self.is_locked}'

    @model_validator(mode='after')
    def check_value_type(self) -> Self:
        """Validates the value type based on the lock mode."""
        match self.mode:
            case LockMode.EXACT:
                pass
            case LockMode.IN_LIST:
                if not isinstance(self.value, Sequence):
                    raise TypeError(
                        'Value should be a Sequence for IN_LIST lock mode'
                    )
            case LockMode.IN_RANGE:
                if not (
                    isinstance(self.value, Sequence) and len(self.value) == 2
                ):
                    raise TypeError(
                        'Value should be a Sequence of length 2 for IN_RANGE lock mode'
                    )
            case LockMode.LARGER_THAN | LockMode.SMALLER_THAN:
                if not isinstance(self.value, (int, float)):
                    raise TypeError(
                        'Value should be a single value for LARGER_THAN or SMALLER_THAN lock modes'
                    )
        return self


class Locker:
    """
    A generic class to be used as a locking mechanism. It contains a collection of locks for different attributes.
    """

    _lock_dictionary: dict[str, Lock]

    def __init__(self, lock_dictionary: dict[str, Lock] | None = None):
        """Initializes the locker to store multiple locks.

        Args:
            lock_dictionary (dict[str, Lock] | None): A optional dictionary of locks to initialize the locker with.
        """
        if lock_dictionary is not None:
            self._lock_dictionary = lock_dictionary
        else:
            self._lock_dictionary = {}

    def add_lock(
        self,
        attribute: str,
        value: Any = None,
        is_hard_lock: bool = True,
        is_locked: bool = True,
        mode: LockMode = LockMode.EXACT,
        comments: str = '',
        owner: str | None = None,
    ):
        """Adds a lock to the locker.

        Args:
            attribute (str): The attribute to lock.
            value (Any): The value of the lock.
            is_hard_lock (bool): Whether the lock is a hard lock or a soft lock
            is_locked (bool): Whether the lock is active or not.
            mode (LockMode): The mode of the lock.
            comments (str): Comments about the lock.
        """
        if owner is None:
            owner = self._get_owner_name(depth=1)

        lock = Lock(
            value=value,
            is_hard_lock=is_hard_lock,
            mode=mode,
            is_locked=is_locked,
            comments=comments,
            owner=owner,
        )
        self._lock_dictionary[attribute] = lock

    def is_valid_value(self, lock: Lock, value: Any):
        """Checks if a value is valid based on the lock mode.

        Args:
            lock (Lock): The lock to check against.
            value (Any): The value to check.

        Returns:
            bool: True if the value is valid, False otherwise.
        """
        if lock.mode == LockMode.EXACT:
            return lock.value == value
        if lock.mode == LockMode.IN_LIST:
            return value in lock.value
        if lock.mode == LockMode.IN_RANGE:
            return value >= lock.value[0] and value <= lock.value[1]
        if lock.mode == LockMode.LARGER_THAN:
            return value >= lock.value
        if lock.mode == LockMode.SMALLER_THAN:
            return value <= lock.value
        return True

    def is_change_allowed(
        self,
        attribute: str,
        value: Any,
        is_hard_lock: bool = True,
        requester: str | None = None,
        is_ignore_owner: bool = False,
    ) -> bool:
        """Check if there is a change to specific value on a specific attribute.

        Args:
            attribute (str): The attribute to check.
            value (Any): The value to check against the lock.
            is_hard_lock (bool): Whether to check for hard locks only.

        Returns:
            bool: True if the change is allowed, False otherwise.
        """

        # Make sure the attribute exists in the locker
        if not self.has_attribute(attribute):
            return True

        # Make sure it is locked
        lock = self._get_lock(attribute)
        if not lock.is_locked:
            return True

        # Check ownership
        if not is_ignore_owner:
            if requester is None:
                requester = self._get_owner_name(depth=1)
            if lock.owner is not None and requester != lock.owner:
                return False

        # If it is locked and you are the owner, make sure the provided value is valid based on the lock mode
        if lock.is_hard_lock is True or is_hard_lock is False:
            return self.is_valid_value(lock, value)

        return True

    def has_attribute(self, attribute: str):
        """Checks if the lock has a specific attribute.

        Args:
            attribute (str): The attribute to check.

        Returns:
            bool: True if the attribute exists, False otherwise.
        """
        return attribute in self._lock_dictionary

    def lock(self, attribute: str):
        """Locks a specific attribute.

        Args:
            attribute (str): The attribute to lock.
        """
        self._get_lock(attribute).is_locked = True

    def unlock(self, attribute: str):
        """Unlocks a specific attribute.

        Args:
            attribute (str): The attribute to unlock.
        """
        self._get_lock(attribute).is_locked = False

    def list_locks(self):
        """Returns the list of locks available."""
        return list(self._lock_dictionary.keys())

    def _get_lock(self, attribute: str) -> Lock:
        """Returns the lock value.

        Args:
            attribute (str): The attribute to get the lock for.

        Returns:
            Lock: The lock for the attribute.
        """

        if not self.has_attribute(attribute):
            raise KeyError(f'Attribute {attribute} not found in locker.')

        return self._lock_dictionary[attribute]

    def _get_owner_name(self, depth: int = 0) -> str | None:
        """Gets the package name of the caller module.

        Args:
            depth (int): The depth in the call stack to get the caller from.

        Returns:
            str | None: The package name of the caller module, or None if not found.
        """
        frame = inspect.currentframe()
        if not frame:
            return None

        # Traverse back: +1 for this function, +depth for caller
        for _ in range(depth + 1):
            if not frame.f_back:
                return None
            frame = frame.f_back

        module = inspect.getmodule(frame)
        if module is not None:
            package_name = module.__name__.split('.')[0]
            return package_name

        return None


class override_lock:
    """
    A context manager to temporarily unlock a specific attribute in a Locker.

    Attributes:
        locker (Locker): The Locker instance containing the locks.
        attribute (str): The attribute to temporarily unlock.
        was_locked (bool): Whether the attribute was originally locked.
    """

    locker: Locker
    attribute: str
    _was_locked: bool

    def __init__(self, locker: Locker, attribute: str):
        """
        Initializes the context manager.

        Args:
            locker (Locker): The Locker instance containing the locks.
            attribute (str): The attribute to temporarily unlock.
        """
        self.locker = locker
        self.attribute = attribute
        self._was_locked = False

    def __enter__(self):
        """Enters the context manager, unlocking the specified attribute."""
        lock = self.locker._get_lock(self.attribute)
        self._was_locked = lock.is_locked
        lock.is_locked = False

    def __exit__(self, exc_type, exc_value, traceback):
        """Exits the context manager, restoring the original lock state."""
        lock = self.locker._get_lock(self.attribute)
        lock.is_locked = self._was_locked
